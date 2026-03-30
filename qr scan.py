import RPi.GPIO as GPIO
from flask import Flask
import sounddevice as sd
import queue, json, threading
from vosk import Model, KaldiRecognizer
import time

# ---------------- GPIO SETUP ----------------
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

RPWM1, LPWM1, REN1, LEN1 = 17, 27, 5, 6
RPWM2, LPWM2, REN2, LEN2 = 22, 23, 24, 25

pins = [RPWM1, LPWM1, REN1, LEN1, RPWM2, LPWM2, REN2, LEN2]
for p in pins:
    GPIO.setup(p, GPIO.OUT)

GPIO.output(REN1, 1)
GPIO.output(LEN1, 1)
GPIO.output(REN2, 1)
GPIO.output(LEN2, 1)

# PWM
pwm_r1 = GPIO.PWM(RPWM1, 1000)
pwm_l1 = GPIO.PWM(LPWM1, 1000)
pwm_r2 = GPIO.PWM(RPWM2, 1000)
pwm_l2 = GPIO.PWM(LPWM2, 1000)

for pwm in [pwm_r1, pwm_l1, pwm_r2, pwm_l2]:
    pwm.start(0)

# ---------------- VARIABLES ----------------
voice_active = False
voice_text = "Waiting..."
current_speed = 0

MAX_FORWARD = 30
MAX_BACKWARD = 20

# ---------------- MOTOR ----------------
def apply(r1,l1,r2,l2):
    pwm_r1.ChangeDutyCycle(r1)
    pwm_l1.ChangeDutyCycle(l1)
    pwm_r2.ChangeDutyCycle(r2)
    pwm_l2.ChangeDutyCycle(l2)

def stop_all():
    apply(0,0,0,0)

# ✅ FORWARD: smooth 0 → 30
def forward():
    global current_speed
    for sp in range(current_speed, MAX_FORWARD+1, 2):
        apply(sp,0,0,sp)
        current_speed = sp
        time.sleep(0.05)

# ✅ BACKWARD: fixed 20
def backward():
    global current_speed

    if current_speed != MAX_BACKWARD:
        slow_stop()  # safety stop before reverse

    apply(0,MAX_BACKWARD,MAX_BACKWARD,0)
    current_speed = MAX_BACKWARD

# ✅ SMOOTH STOP: gradual decrease
def slow_stop():
    global current_speed
    for sp in range(current_speed, -1, -2):
        apply(sp,sp,sp,sp)
        time.sleep(0.05)
    stop_all()
    current_speed = 0

# TURNS
def left():
    slow_stop()
    apply(10,0,10,0)

def right():
    slow_stop()
    apply(0,10,0,10)

# ---------------- VOICE ----------------
q = queue.Queue()

def callback(indata, frames, time_info, status):
    q.put(bytes(indata))

def voice_thread():
    global voice_text, voice_active

    model = Model("vosk-model-small-en-us-0.15")
    rec = KaldiRecognizer(model, 16000)

    with sd.RawInputStream(samplerate=16000, blocksize=8000,
                           dtype='int16', channels=1, callback=callback):
        while True:
            data = q.get()

            if not voice_active:
                continue

            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                text = result.get("text","")
                voice_text = text

                if "forward" in text or "up" in text:
                    forward()
                elif "backward" in text:
                    backward()
                elif "left" in text:
                    left()
                elif "right" in text:
                    right()
                elif "stop" in text:
                    slow_stop()

threading.Thread(target=voice_thread, daemon=True).start()

# ---------------- FLASK ----------------
app = Flask(__name__)

style = """
<style>
body { text-align:center; font-family:Arial; background:#111; color:white; }
button {
    width:220px;
    height:65px;
    font-size:18px;
    margin:10px;
    border:none;
    border-radius:15px;
    color:white;
}
.forward { background:#28a745; }
.backward { background:#dc3545; }
.left { background:#fd7e14; }
.right { background:#fd7e14; }
.stop { background:#000000; }
.mode { background:#007bff; }
.back { background:#6c757d; }
.next { background:#6f42c1; }
</style>
"""

# SCREEN 1
@app.route('/')
def home():
    return style + '''
    <h1>G4 AUTONOMOUS WHEELCHAIR</h1>
    <a href="/mode"><button class="next">NEXT</button></a>
    '''

# SCREEN 2
@app.route('/mode')
def mode():
    global voice_active
    voice_active = False

    return style + '''
    <h2>Select Mode</h2>

    <a href="/voice"><button class="mode">VOICE MODE</button></a><br>
    <a href="/manual"><button class="mode">MANUAL MODE</button></a><br><br>

    <a href="/"><button class="back">BACK</button></a>
    '''

# VOICE MODE
@app.route('/voice')
def voice():
    global voice_active
    voice_active = True

    return style + f'''
    <h2>VOICE MODE</h2>
    <h3>Command: {voice_text}</h3>
    <a href="/mode"><button class="back">BACK</button></a>

    <script>
    setTimeout(()=>location.reload(),1000);
    </script>
    '''

# MANUAL MODE
@app.route('/manual')
def manual():
    return style + '''
    <h2>MANUAL CONTROL</h2>

    <a href="/forward"><button class="forward">FORWARD</button></a><br>

    <a href="/left"><button class="left">LEFT</button></a>
    <a href="/stop"><button class="stop">STOP</button></a>
    <a href="/right"><button class="right">RIGHT</button></a><br>

    <a href="/backward"><button class="backward">BACKWARD</button></a><br>

    <a href="/mode"><button class="back">BACK</button></a>
    '''

# BUTTON ROUTES
@app.route('/forward')
def f():
    forward()
    return manual()

@app.route('/backward')
def b():
    backward()
    return manual()

@app.route('/left')
def l():
    left()
    return manual()

@app.route('/right')
def r():
    right()
    return manual()

@app.route('/stop')
def s():
    slow_stop()
    return manual()

# RUN
app.run(host='0.0.0.0', port=5000)
