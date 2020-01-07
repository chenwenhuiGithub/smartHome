#!/usr/bin/env python
# -*- coding: utf8 -*-

import signal
import time
import threading
import re
import sys
import subprocess
import itchat
from itchat.content import TEXT, RECORDING
import serial
import Motor
import Camera
import Speech
import Execute
from snowboy import snowboydecoder

sender = 'filehelper' # for wechat
snowboyEnable = False

ser = serial.Serial("/dev/ttyAMA0", 9600)
if ser.isOpen():
    print("/dev/ttyAMA0 open success")

motor = Motor.Motor()
camera = Camera.Camera()
speech = Speech.Speech()
execute = Execute.Execute()

def handler_sigint(signalnum, frame):
    ser.close()
    print("process exit")
    exit(0)


# **************** commands callback **************************************
def commandImage():
    speech.Speech_play("./resources/camera.wav", "wav")
    fileName = camera.Camera_saveImage()
    itchat.send('@img@%s' %fileName, toUserName=sender)
    speech.Speech_play("./resources/saveImageDone.mp3", "mp3") # u"照片拍摄完成，已发送到微信"

def commandVideo():
    fileName = camera.Camera_saveVideo(3000)
    itchat.send('@vid@%s' %fileName, toUserName=sender)
    speech.Speech_play("./resources/saveVideoDone.mp3", "mp3") # u"视频拍摄完成，已发送到微信"

def parseAngle(recordText):
    angleStr = re.sub(r'\D', "", recordText) # parse number
    angle = int(angleStr)
    if angle > 90:
        angle = 90
    return angle

def commandCameraLeft(angle):
    def motorForwardThread(angle):
        motor.Motor_forward(angle)

    threading.Thread(target=motorForwardThread, args=(angle,)).start()
    fileName = camera.Camera_saveVideo(angle*115) # 0.02*4*(angle/0.7)*1000
    itchat.send('@vid@%s' %fileName, toUserName=sender)
    speech.Speech_play("./resources/cameraLeftDone.mp3", "mp3") # u"摄像头左转完成"

def commandCameraRight(angle):
    def motorBackwardThread(angle):
        motor.Motor_backward(angle)

    threading.Thread(target=motorBackwardThread, args=(angle,)).start()
    fileName = camera.Camera_saveVideo(angle*115) # 0.02*4*(angle/0.7)*1000
    itchat.send('@vid@%s' %fileName, toUserName=sender)
    speech.Speech_play("./resources/cameraRightDone.mp3", "mp3") # u"摄像头右转完成"

def commandCleanCache():
    subprocess.call("rm -f ./capture/*.jpg ./capture/*.mp4 ./capture/*.mp3 ./capture/*.wav ./capture/*.pcm", shell=True)
    subprocess.call("rm -f ./*.wav ./*.mp3", shell=True)
    speech.Speech_play("./resources/cleancacheDone.mp3", "mp3") # u"缓存清理完成"

def parseInfrared(recordText):
    for k, v in tvInfraredCodes.items():
        if k in recordText:
            return v

def comamndTv(*infraredCode): # parse function return tuple
    str = ''
    for item in infraredCode:
        temp = hex(item) # 0x6 or 0x6a
        if len(temp) == 3:
            str = str + "0" + temp[2]
        else:
            str = str + temp[2] + temp[3]
    sendData = bytes.fromhex(str)
    print("sendData", sendData) # sendData <class 'bytes'> b'\x01#\xab\xff\n'
    ser.write(sendData)

def commandNotHitted(recordText):
    respText = speech.Speech_emotibot(recordText)
    respFile = speech.Speech_tts(respText)
    print("respText: %s" %respText)
    speech.Speech_play(respFile, "mp3")


# **************** itchat procedure **************************************
@itchat.msg_register([TEXT])
def text_reply(msg):
    global sender
    recordText = msg.text
    sender = msg['FromUserName']
    if msg['ToUserName'] == 'filehelper': # for test
        sender = 'filehelper'

    try:
        print("recordText: %s" %recordText)
        execute.process(recordText)
    except:
        print("text_reply error: ", sys.exc_info()[0])
    finally:
        sender = 'filehelper' # switch back to filehelper after friends procedure

@itchat.msg_register([RECORDING])
def recording_reply(msg):
    global sender
    sender = msg['FromUserName']
    if msg['ToUserName'] == 'filehelper':
        sender = 'filehelper'

    msg['Text'](msg['FileName']) # save mp3 file
    try:
        recordFile = speech.Speech_convertMp3ToPcm(msg['FileName'])
        recordText = speech.Speech_asr(recordFile, "pcm")
        print("recordText: %s" %recordText)
        execute.process(recordText)
    except:
        print("recording_reply error: ", sys.exc_info()[0])
    finally:
        sender = 'filehelper' # switch back to filehelper after friends procedure

def threadItChat():
    itchat.auto_login(enableCmdQR=2, hotReload=True)
    itchat.run()


# **************** record procedure **************************************
def threadRecord():
    while True:
        try:
            recordFile = speech.Speech_record()
            recordText = speech.Speech_asr(recordFile, "wav")
            print("recordText: %s" %recordText)
            execute.process(recordText)
        except:
            print("threadRecord error: ", sys.exc_info()[0])


# **************** snowboy procedure **************************************
def cbAudioRecorder(recordFile):
    try:
        recordText = speech.Speech_asr(recordFile, "wav")
        print("recordText: %s" %recordText)
        execute.process(recordText)
    except:
        print("cbAudioRecorder error: ", sys.exc_info()[0])

def threadSnowboy():
    detector = snowboydecoder.HotwordDetector("./resources/xiaohong.pmdl", sensitivity=0.5)
    detector.start(audio_recorder_callback=cbAudioRecorder)
    detector.terminate()


# **************** serial procedure **************************************
def threadSerial():
    while True:
        data = ser.read(5)
        recvData = data.hex()
        print("recvData", recvData) # recvData <class 'str'> 0123abff0a


# key: hit words, value: v1-command process callback, v2-parameters parse callback
commands = {
(u"拍照", u"拍张照"):(commandImage,),
(u"拍视频", u"拍个视频"):(commandVideo,),
(u"左转",):(commandCameraLeft, parseAngle),
(u"右转",):(commandCameraRight, parseAngle),
(u"清缓存", u"清除缓存", u"清空缓存", u"清理缓存"):(commandCleanCache,),
(u"左边", u"右边", u"向上", u"上面", u"向下", u"下面", u"声音大", u"声音调大", u"声音小", u"声音调小",
 u"确定", u"返回", u"主页", u"开电视", u"关电视", u"关闭电视"):(comamndTv, parseInfrared)}

tvInfraredCodes = {
u"左":(0x01, 0x21, 0xa1, 0xff, 0x0a),
u"右":(0x02, 0x22, 0xa2, 0xff, 0x0a),
u"上":(0x03, 0x23, 0xa3, 0xff, 0x0a),
u"下":(0x04, 0x24, 0xa4, 0xff, 0x0a),
u"大":(0x05, 0x25, 0xa5, 0xff, 0x0a),
u"小":(0x06, 0x26, 0xa6, 0xff, 0x0a),
u"确定":(0x07, 0x27, 0xa7, 0xff, 0x0a),
u"返回":(0x08, 0x28, 0xa8, 0xff, 0x0a),
u"主页":(0x09, 0x29, 0xa9, 0xff, 0x0a),
u"开":(0x0a, 0x2a, 0xaa, 0xff, 0x0a),
u"关":(0x0b, 0x2b, 0xab, 0xff, 0x0a)}


if __name__ == '__main__':
    print("process begin")
    signal.signal(signal.SIGINT, handler_sigint)

    for k, v in commands.items():
        execute.registerProcedure(k, v)
    execute.registerNotHittedProcedure(commandNotHitted)

    threading.Thread(target=threadItChat).start()
    threading.Thread(target=threadSerial).start()
    if snowboyEnable:
        threading.Thread(target=threadSnowboy).start()
    else:
        threading.Thread(target=threadRecord).start()

