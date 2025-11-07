import asyncio
import json
import math
import os
import signal
import subprocess
import sys
import time
import threading
import pigpio
import socket

from readonly import RobotBase, MOTORS

OPERATOR_IP = ""  # your laptop/pc ip address on IC2026 Network
OPERATOR_PORT = 5600  # the port for video streaming
TEAM_ID = 9  # Your team ID

PI_IP = ""  # Your pi IP
PI_PORT = 5005  #

MIN_DUTY_FLOOR = 30
PURE_DC_THRESHOLD = 80
PWM_FREQ_HZ = 10000

### Bind Socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((PI_IP, PI_PORT))

### Input Receiving Loop
inputQ = []

# Motor
motor_map = {
    "FR":"MOTOR 1",
    "FL":"MOTOR 2",
    "BR":"MOTOR 3",
    "BL":"MOTOR 4"
}



class Robot(RobotBase):
    def __init__(self, team_id):
        super().__init__(team_id)
        ### Initialization/Start Up
        self.pi = pigpio.pi()
        if not self.pi.connected:
            print("[Error] Could not connect to pigpio daemon.")
            sys.exit(1)
        print("[Init] Pigpio connected.")

        # pass

        ### Socket Receive Thread
        threading.Thread(target=get_input, daemon=True).start()
    def get_input():
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                msg = json.loads(data.decode("utf-8"))
                inputQ.append(msg)
                print(f"[Received from {addr}] {msg}")
            except Exception as e:
                print("[Receiver Error]", e)

    def apply_motor(name, norm):
        norm = clamp(norm, -1.0, 1.0) * DIR_OFFSET[name]
        pins = MOTORS[name]

        if abs(norm) < 1e-3:
            pi.set_PWM_dutycycle(pins["EN"], 0)
            pi.write(pins["IN1"], 0)
            pi.write(pins["IN2"], 0)
            return

        forward = norm > 0
        pi.write(pins["IN1"], 1 if forward else 0)
        pi.write(pins["IN2"], 0 if forward else 1)

        pct = int(abs(norm) * 100)
        if pct >= PURE_DC_THRESHOLD:
            pi.write(pins["EN"], 1)
        else:
            pct = max(MIN_DUTY_FLOOR, pct)
            duty = pct * 255 // 100
            pi.set_PWM_dutycycle(pins["EN"], duty)

    def tank_drive(self):
        if len(inputQ) > 0:
            inputJSON = inputQ.pop(0)
            self.set_motor("FL", inputJSON["Left"])
            self.set_motor("BL", inputJSON["Left"])
            self.set_motor("FR", inputJSON["Right"])
            self.set_motor("BR", inputJSON["Right"])

    def mecanum_drive(self):
        if len(inputQ) > 0:
            inputJSON = inputQ.pop(0)
            vx = inputJSON["vx"]
            vy = inputJSON["vy"]
            rot = inputJSON["rot"]

            fl = vy + vx + rot
            fr = -vy + vx - rot
            bl = -vy + vx + rot
            br = vy + vx - rot
           
            scale = max(1.0, abs(fl), abs(fr), abs(bl), abs(br))
            fl /= scale; fr /= scale; rl /= scale; rr /= scale # normalize each speed

            self.set_motor("FL", fl)
            self.set_motor("BL", bl)
            self.set_motor("FR", fr)
            self.set_motor("BR", br)

    def run(self):
        try:
            while True:
                # Call the drive handler
                self.tank_drive()   # or self.mecanum_drive() if using Mecanum
                time.sleep(1 / SEND_HZ)  

        except KeyboardInterrupt:
            sys.stderr.write("\n[Shutdown] Keyboard interrupt\n")
        except Exception as e:
            sys.stderr.write(f"[Runtime Error] {e}\n")
        finally:
            self.cleanup()  


    def stream(self):
        cmd = (
            f"rpicam-vid -t 0 --width 1280 --height 720 --framerate 30 "
            f"--codec h264 --bitrate 4000000 --profile baseline --intra 30 --inline "
            f"--nopreview -o - | "
            f"gst-launch-1.0 -v fdsrc ! h264parse ! "
            f"rtph264pay config-interval=1 pt=96 ! "
            f"udpsink host={OPERATOR_IP} port={OPERATOR_PORT} sync=false async=false"
        )
   
        self.stream_proc = subprocess.Popen(cmd, shell=True, preexec_fn=os.setsid, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[Video] Stream started -> {OPERATOR_IP}:{OPERATOR_PORT}")


    def set_motor(self):
        value = max(-1.0, min(1.0, value))
        pins = MOTORS[motor]
        
        if abs(value) < 1e-3:
            self.pi.set_PWM_dutycycle(pins["EN"], 0)
            self.pi.write(pins["IN1"], 0)
            self.pi.write(pins["IN2"], 0)
            return
        
        forward = value > 0
        self.pi.write(pins["IN1"], 1 if forward else 0)
        self.pi.write(pins["IN2"], 0 if forward else 1)
        
        pct = int(abs(value) * 100)
        if pct >= PURE_DC_THRESHOLD:
            self.pi.write(pins["EN"], 1)
        else:
            pct = max(MIN_DUTY_FLOOR, pct)
            duty = pct * 255 // 100
            self.pi.set_PWM_dutycycle(pins["EN"], duty)


    def cleanup(self):
        if self.stream_proc and self.stream_proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.stream_proc.pid), signal.SIGTERM)
                self.stream_proc.wait(timeout=2)
            except:
                pass
            print("[Video] Stream stopped")
        self.stream_proc = None

        for receiver in self.ir_receivers:
            receiver.cleanup()


if __name__ == "__main__":
    team_id = 9  # your team id here
    robot = Robot(team_id)
    config = None
    try:
        with open("../config.json") as file:
            config = json.load(file)
    except FileNotFoundError:
        print(f"Config File not found in parent directory!")
    except json.JSONDecodeError:
        print(f"Failed to decode config file!")

    robot = Robot(config)
    robot.stream()
    try:
        robot.run()
    except KeyboardInterrupt:
        print("\n[Shutdown] Received interrupt")
    except Exception as e:
        print(f"[Error] {e}")
    finally:
        robot.cleanup()
