import json
import socket
import subprocess
import sys
import time
import threading
import pygame
import os
import KeyboardInterrupt
# ============ USER CONFIG ============
PI_IP = ""    # Your Pi's IP on IC2026 network
PI_PORT = 5005

AUTO_LAUNCH_GSTREAMER = True
GST_RECEIVER_CMD = (
    'gst-launch-1.0 -v udpsrc port=5600 caps='
    '"application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000,packetization-mode=1" '
    '! rtpjitterbuffer latency=50 ! rtph264depay ! h264parse ! d3d11h264dec ! autovideosink sync=false'
)
GST_RECEIVER_CMD_AVD = (
    'gst-launch-1.0 -v udpsrc port=5600 caps="'
    'application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000,packetization-mode=1" '
    '! rtpjitterbuffer latency=50 ! rtph264depay ! h264parse ! avdec_h264 ! autovideosink sync=false'
)

SEND_HZ = 30

### Sockets
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # create a UPD/datagram socket
addr = (PI_IP, PI_PORT)

### Video Stream
gst_proc = None
def open_stream():
        global gst_proc

        if AUTO_LAUNCH_GSTREAMER:
            try:
                gst_proc = subprocess.Popen(GST_RECEIVER_CMD, shell=True) # run the command we wrote in the shell
                print("[Video] GStreamer started")
            except Exception as e:
                print(f"[Video] Failed: {e}")

### Clean Up

DRIVE_MODE = "tank" ### or "macanum"
### Input Loop
def input_loop():
    while True:
        try:
            if DRIVE_MODE == "tank":
                # --- Tank Drive ---
                left = 0
                if keyboard.is_pressed("w"):
                    left = 1
                elif keyboard.is_pressed("s"):
                    left = -1

                right = 0
                if keyboard.is_pressed("up"):
                    right = 1
                elif keyboard.is_pressed("down"):
                    right = -1

                payload = {"Left": left, "Right": right}

            elif DRIVE_MODE == "mecanum":
                # --- Mecanum Drive ---
                vx = vy = rot = 0

                if keyboard.is_pressed("w"):
                    vy = 1
                elif keyboard.is_pressed("s"):
                    vy = -1

                if keyboard.is_pressed("a"):
                    vx = -1
                elif keyboard.is_pressed("d"):
                    vx = 1

                if keyboard.is_pressed("right"):
                    rot = 1
                elif keyboard.is_pressed("left"):
                    rot = -1

                payload = {"vx": vx, "vy": vy, "rot": rot}

             # === Send and Receive JSON ===
            try:
                sock.sendto(json.dumps(payload).encode("utf-8"), (PI_IP, PI_PORT))  # send our json to Pi
                sock.settimeout(0.001)  # small timeout to not block the thread
                try:
                    data, addr = sock.recvfrom(1024)  # check for response
                    response = json.loads(data.decode("utf-8"))

                    # sensor feedback
                    if response.get("is_self_hit", False):
                        print(f"[GUI] Self-hit detected in response: {response}")

                except (socket.timeout, json.JSONDecodeError):
                    pass
                finally:
                    sock.settimeout(None)

            except Exception as e:
                print(f"UDP error: {e}")

            time.sleep(1 / SEND_HZ)

        except Exception as e:
            print("[Input Loop Error]", e)
            break
input_thread = threading.Thread(target=input_loop, daemon=True)

### Main Loop
def main():
    ### Open Stream

    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    clock = pygame.time.Clock()
    running = True
    open_stream()
    

    ### Start Input Thread
    input_thread.start()

    running = True
    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    ### Start Cleanup

                    running = False
                    pygame.quit()
                    screen.fill("black")
                    pygame.display.flip()
                    clock.tick(SEND_HZ)
    except Exception as e:
        print(f"[Error] {e}")
    finally:
        cleanup()  # ensure GStreamer and socket are properly closed
        pygame.quit()
   
if __name__ == "__main__":
    main()