from flask import Flask, render_template
from multiprocessing import Process,Pipe
import time

app = Flask(__name__)

def detachedProcessFunction(wait_time,conC):
    i=0
    conC.send("send_1")
    while i<wait_time:
        i = i+1
        print ("loop running" + str(i))
        time.sleep(1)
    conC.send("send_2")

@app.route('/')
def start():
    global p
    conP,conC = Pipe()
    p = Process(target=detachedProcessFunction, args=(15,conC))
    p.start()
    print(conP.recv())
    print(conP.recv())
    return render_template('game.html')

if __name__ == '__main__':
    app.run(debug=True)