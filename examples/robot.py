from Adafruit_Thermal import *
import RPi.GPIO as GPIO
import time
import os
from PIL import Image
import subprocess
import select
import socket
import errno


# GPIO PINS
BUTTON_HALT = 6
BUTTON_PRINT = 5
READY_LED = 4
BUSY_LED = 27
PRINTING_LED = 17

EYE_1_LED = 18
EYE_2_LED = 22

# Store the print number in a text file so it persists between boots
global imageNum
imageNum = 1
with open ('imageNum.txt', 'r') as readFile:
    val = readFile.read()
    imageNum = int(val) + 1
    readFile.close()

print("imagNum: " + str(imageNum))


# Init GPIO states
GPIO.setmode(GPIO.BCM)
GPIO.setup(READY_LED, GPIO.OUT)
GPIO.setup(BUSY_LED, GPIO.OUT)
GPIO.setup(PRINTING_LED, GPIO.OUT)
GPIO.setup(EYE_1_LED, GPIO.OUT)
GPIO.setup(EYE_2_LED, GPIO.OUT)
GPIO.setup(BUTTON_PRINT, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BUTTON_HALT, GPIO.IN, pull_up_down=GPIO.PUD_UP)

GPIO.output(READY_LED, GPIO.LOW)
GPIO.output(PRINTING_LED, GPIO.HIGH)


# Socket server is used to communicate with the Processing app that generates the images
print('starting socket server...')
HOST = ''
PORT = 5204
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

s.bind((HOST, PORT))
s.listen(1)

GPIO.output(BUSY_LED, GPIO.HIGH)
IMAGE_OUTPUT_FILE = "build/application.linux-armv6hf/output/image.png"


# launch processing app as subprocess
print('launching p5')
subprocess.Popen(['xvfb-run', 'build/application.linux-armv6hf/build'])

conn, addr = s.accept()
conn.setblocking(False)
print('Connected by', addr)

printer = Adafruit_Thermal("/dev/ttyUSB0", 9600, timeout=5)

# Flash the eye LEDs in a pattern
def flashEyes():
    GPIO.output(EYE_1_LED, GPIO.LOW)
    GPIO.output(EYE_2_LED, GPIO.LOW)
    time.sleep(0.5)
    GPIO.output(EYE_1_LED, GPIO.HIGH)
    time.sleep(0.3)
    GPIO.output(EYE_1_LED, GPIO.LOW)
    GPIO.output(EYE_2_LED, GPIO.HIGH)
    time.sleep(0.3)
    GPIO.output(EYE_1_LED, GPIO.HIGH)
    GPIO.output(EYE_2_LED, GPIO.LOW)
    time.sleep(0.3)
    GPIO.output(EYE_1_LED, GPIO.LOW)
    GPIO.output(EYE_2_LED, GPIO.HIGH)
    time.sleep(0.3)
    GPIO.output(EYE_1_LED, GPIO.LOW)
    GPIO.output(EYE_2_LED, GPIO.LOW)
    time.sleep(0.5)
    GPIO.output(EYE_1_LED, GPIO.HIGH)
    GPIO.output(EYE_2_LED, GPIO.HIGH)
    

# move the printed image to the archive folder
def archiveImage(num):
    filename = "archive/image-" + str(num) + ".png"
    os.rename(IMAGE_OUTPUT_FILE, filename)
    with open ('imageNum.txt', 'w') as file:
        file.write(str(imageNum))
        file.close()


# print the image (and text)
def doPrinting(num):
    print("doPrinting()")
    GPIO.output(READY_LED, GPIO.LOW)
    GPIO.output(BUSY_LED, GPIO.HIGH)
    
    GPIO.output(BUSY_LED, GPIO.LOW)
    GPIO.output(PRINTING_LED, GPIO.HIGH)
    
    try:
        img = Image.open(IMAGE_OUTPUT_FILE)
    except:
        showErrorState("ERROR: No image found")
        return
    
    # MAX CHARS: 32 "12345678901234567890123456789012"
    printer.println("SPRING FOR ZINES!  April 8, 2018")
    printer.println("--------------------------------")
    
    printer.printImage(img)
    
    printer.println("VOMIT COMIC #" + str(num))
    printer.println("www.cadinbatrack.com/vomit-comic")
    printer.feed(3)
    
    archiveImage(num)


# shut down the Pi safely
def shutdown():
    GPIO.output(READY_LED, GPIO.LOW)
    GPIO.output(BUSY_LED, GPIO.HIGH)
    GPIO.output(PRINTING_LED, GPIO.HIGH)
    GPIO.output(EYE_1_LED, GPIO.LOW)
    GPIO.output(EYE_2_LED, GPIO.LOW)
    os.system("sudo halt")


def showErrorState(e):
    print(e)
    GPIO.output(READY_LED, GPIO.LOW)
    
    GPIO.output(PRINTING_LED, GPIO.LOW)
    GPIO.output(BUSY_LED, GPIO.HIGH)
    time.sleep(0.5)
    GPIO.output(PRINTING_LED, GPIO.HIGH)
    GPIO.output(BUSY_LED, GPIO.LOW)
    time.sleep(0.5)
    GPIO.output(PRINTING_LED, GPIO.LOW)
    GPIO.output(BUSY_LED, GPIO.HIGH)
    time.sleep(0.5)
    GPIO.output(PRINTING_LED, GPIO.HIGH)
    GPIO.output(BUSY_LED, GPIO.LOW)
    time.sleep(0.5)
    GPIO.output(BUSY_LED, GPIO.HIGH)
    GPIO.output(PRINTING_LED, GPIO.HIGH)
    time.sleep(2)
    
    if e != "":
        printer.println(e)
        printer.feed(2)
    
    GPIO.output(PRINTING_LED, GPIO.LOW)
    GPIO.output(BUSY_LED, GPIO.LOW)
    

systemIsReady = True
def showReadyState():
    flashEyes()
    GPIO.output(BUSY_LED, GPIO.LOW)
    GPIO.output(PRINTING_LED, GPIO.LOW)
    GPIO.output(READY_LED, GPIO.HIGH)
    global systemIsReady
    systemIsReady = True


time.sleep(1)
showReadyState()

print('entering loop"')

try:
    print('try')
    while True:
        
        # get data from the socket connection
        data = ""
        try:
            data = conn.recv(1024)
        except IOError as e:
            if e.errno == errno.EWOULDBLOCK:
                pass
        
        # if Processing generated an image, print it
        if data == "image ready":
            print("image ready")
            flashEyes()
            doPrinting(imageNum)
            imageNum += 1
            showReadyState()
        
        # get input states from the button GPIO pins
        input_state = GPIO.input(BUTTON_PRINT)
        halt_state = GPIO.input(BUTTON_HALT)
    	
    	# print button pressed
        if input_state == False:
            time.sleep(0.2)
            print("button")

            GPIO.output(READY_LED, GPIO.LOW)
            GPIO.output(BUSY_LED, GPIO.HIGH)
            
            #send message to Processing 
            conn.send("generate image")
            
        
    	# halt (shutdown) button pressed
        if halt_state == False:
            startTime = time.time()
            time.sleep(0.2)
            
            # only start shutdown if the halt button is held for 2 seconds
            while GPIO.input(BUTTON_HALT) == GPIO.LOW:
                time.sleep(0.1)
                length = time.time() - startTime
                if length > 2:
                  shutdown()
        time.sleep(0.1)
 
# cleanup GPIO and socket connection before quitting             
finally:
    print('finally')
    GPIO.cleanup()
    conn.close()


