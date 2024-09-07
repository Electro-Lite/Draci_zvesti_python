from flask           import Flask,render_template,request,url_for,redirect,session
from flask_session   import Session
from multiprocessing import Process, Pipe
import game

app = Flask(__name__)
app.config['SESSION_TYPE'] = 'filesystem'  # Store session data on the server-side (file system)
app.config['SESSION_PERMANENT'] = False     # The session is not permanent and will expire when the browser closes
app.config['SESSION_USE_SIGNER'] = True     # Sign the cookie to prevent tampering
app.secret_key = 'exceptionnaly_sekret_kee'
app.config['SESSION_TYPE'] = 'redis'  # Use Redis instead of filesystem
app.config['SESSION_PERMANENT'] = False  # Optional: Set this to False to make sessions non-permanent

Session(app)

def checkSession():
    print (session)
    if 'username' in session:
        username = session['username']
        return username
    else:
        return ""

@app.route("/", methods=['POST','GET'])
def index():
    print("user: "+checkSession())
    if(checkSession()==""):
        return login()
    return render_template("index.html",txt="sup bro")

@app.route("/place_card", methods=['POST'])
def place_card():
    print(request.get_json()["board_position"])
    board_pos     = int( request.get_json()["board_position"])
    card_position = int( request.get_json()["card_position"])
    return "board_position: " + request.get_json()["board_position"] + "\n card_position: " + request.get_json()["card_position"]

@app.route('/runGame', methods=['POST'])
def submit():
    p_conn,ch_conn = Pipe()
    game_run = Process(target=game.run, args=(game.player(1,"pl"),game.player(2,"rnd"),ch_conn,))
    game_run.start()
    print("recieved: ",end="")
    print(p_conn.recv())
    game_run.join()
    game_run.close()
    return render_template("game.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['username'] = request.form['username']
        return redirect(url_for('index'))
    return '''
        <form method="post">
            <p><input type=text name=username>
            <p><input type=submit value=Login>
        </form>
    '''
    
app.run(host="0.0.0.0",port = 80,debug=True, use_debugger=False, use_reloader=False)
