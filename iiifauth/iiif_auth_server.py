import os
import re
import json
import uuid
import sqlite3
from datetime import timedelta

from flask import (
    Flask, make_response, request, session, g, url_for,
    render_template, redirect, send_file, jsonify
)

app = Flask(__name__)
app.permanent_session_lifetime = timedelta(minutes=10)
app.secret_key = 'Set a sensible secret key here'
app.database = os.path.join(app.root_path, 'iiifauth.db')
app.config.update(dict(
    SERVER_NAME=os.environ.get('IIIFAUTH_SERVER_NAME', None),
    SESSION_COOKIE_SAMESITE='None',
    SESSION_COOKIE_SECURE=True
))

# some globals
APP_PATH = os.path.dirname(os.path.abspath(__file__))
MEDIA_ROOT = os.path.join(APP_PATH, 'media')
PROTECTED_IMAGE_SERVICE = "PROTECTED_IMAGES"


@app.before_request
def func():
    """Make our Flask sessions last longer than the browser window lifetime"""
    session.permanent = True
    session.modified = True


def resolve(identifier):
    """Resolves a iiif identifier to the resource's path on disk."""
    return os.path.join(MEDIA_ROOT, identifier)


@app.route('/')
def index():
    return render_template('index.html', images=os.listdir(MEDIA_ROOT))


@app.route('/debug.json')
def debug():
    return jsonify({
        "url": request.url
    })


def make_acao_response(response_object, status=None, cache=None, origin=None):
    """We're handling CORS directly for clarity"""
    resp = make_response(response_object, status)
    resp.headers['Access-Control-Allow-Origin'] = origin or '*'
    if cache is None:
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    else:
        resp.headers['Cache-Control'] = 'public, max-age=120'
    return resp


def preflight():
    """Handle a CORS preflight request"""
    resp = make_acao_response('', 200)
    resp.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS, HEAD'
    resp.headers['Access-Control-Allow-Headers'] = 'Authorization'
    return resp


@app.route('/img/<identifier>/info.json', methods=['GET', 'OPTIONS', 'HEAD'])
def image_info(identifier):
    """
        Return the info.json, with the correct HTTP status code,
        and decorated with the right auth services

        Handle CORS explicitly for clarity
    """
    print("METHOD:", request.method)
    if request.method == 'OPTIONS':
        print('CORS preflight request for', identifier)
        return preflight()

    print('info.json request for', identifier)
    info = {
        "id": url_for('image', identifier=identifier, _external=True),
        "metadata": {
            "foo": "bar",
            "baz": "(other image metadata useful to the client in constructing image requests)"
        }
    }
    if identifier == "protected.jpg":
        info["authService"] = {
            "id": url_for('cookie_service', _external=True),
            "label": "Login to Example Institution",
            "header": "Please Log In",
            "description": "Please log in with your example account to view this image.",
            "confirmLabel": "Login",
            "failureHeader": "Authentication Failed",
            "failureDescription": "<a href=\"http://example.org/policy\">Access Policy</a>",
            "tokenService": url_for('token_service', _external=True)
        }

    if authorise_probe_request(identifier):
        return make_acao_response(jsonify(info), 200)

    print('The user is not authed for this resource')

    return make_acao_response(jsonify(info), 401)


def authorise_probe_request(identifier):
    """
        Authorise info.json or probe request based on token
        This should not be used to authorise DIRECT requests for content resources
    """
    if identifier == "open.jpg":
        print(f'{identifier} is open, no auth required')
        return True

    service_id = None
    match = re.search('Bearer (.*)', request.headers.get('Authorization', ''))
    if match:
        token = match.group(1)
        print(f'token {token} found')
        db_token = query_db('select * from tokens where token=?', [token], one=True)
        if db_token:
            service_id = db_token['service_id']
            print(f'service_id {service_id} found')
    else:
        print('no Authorization header found')

    if not service_id:
        print('requires access control and no service_id found')
        return False

    if service_id == PROTECTED_IMAGE_SERVICE:
        print('User has access to service', PROTECTED_IMAGE_SERVICE, ' - request authorised')
        return True

    print('info request is NOT authorised')
    return False


def get_session_id():
    """Helper for session_id"""
    return session.get('session_id', None)


def authorise_resource_request(identifier):
    """
        Authorise image API requests based on Cookie (or possibly other mechanisms)
        This method should not accept a token as evidence of identity
    """
    if identifier == "open.jpg":
        print(f'{identifier} is open, no auth required')
        return True

    # does the request have a cookie acquired from this image's cookie service(s)?
    # In this demo, there is only cookie service.
    # In real life there may be many - or also just one, depending on requirements.
    if session.get(PROTECTED_IMAGE_SERVICE, None):
        # we stored the user's access to this service in the session.
        # There will also be a row in the tokens table, but we don't need that
        # This is an example implementation, there are many ways to do this.
        return True

    # handle other possible authorisation mechanisms, such as IP
    return False


@app.route('/img/<identifier>')
def image(identifier):
    if authorise_resource_request(identifier):
        # Just serve the image
        return send_file(resolve(identifier), mimetype="image/jpg")

    return make_response("Not authorised", 401)


@app.route('/auth/cookie', methods=['GET', 'POST'])
def cookie_service():
    """Cookie service (might be a login interaction pattern. Doesn't have to be)"""
    origin = request.args.get('origin')
    if origin is None:
        # http://iiif.io/api/auth/1.0/#interaction-with-the-access-cookie-service
        return make_response("Error - no origin supplied", 400)

    return handle_login(origin, 'login.html')


def handle_login(origin, template):
    """
        Handle login GETs and POSTs
    """
    # We only have one protected resource
    if authorise_resource_request("protected.jpg"):
        return successful_login(origin)

    error = None
    if request.method == 'POST':
        if request.form['username'] != 'username':
            error = 'Invalid username'
        elif request.form['password'] != 'password':
            error = 'Invalid password'
        else:
            return successful_login(origin)

    return render_template(template, error=error)


def successful_login(origin):
    """
        Create a new session and direct the user to a self-closing window
    """
    resp = redirect(url_for('post_login'))
    # create a session with permission to see protected.jpg
    make_session("protected.jpg", origin)
    return resp


def make_session(identifier, origin):
    """
        Establish a session for this user and this resource.
        This is not a production application!
    """
    # Get or create a session ID to keep track of this user's permissions
    session_id = get_session_id()
    if session_id is None:
        session_id = uuid.uuid4().hex
        session['session_id'] = session_id
    print("This user's session is", session_id)

    if origin is None:
        origin = "[No origin supplied]"
    print('User authed for service ', PROTECTED_IMAGE_SERVICE)
    print('origin is ', origin)
    # The token can be anything, but you shouldn't be able to
    # deduce the cookie value from the token value.
    # In this demo the client cookie is a Flask session cookie,
    # we're not setting an explicit IIIF auth cookie. You might in a real app,
    # or you might be delegating off to some organisational SSO and still have
    # no idea what the cookie is.

    # Store the fact that user can access this service in the session
    session[PROTECTED_IMAGE_SERVICE] = True
    # Now store a token associated that represents the user's access to this service
    token = uuid.uuid4().hex
    print('minted token:', token)
    print('session id:', session_id)

    db = get_db()
    db.execute("delete from tokens where session_id=? and service_id=?",
               [session_id, PROTECTED_IMAGE_SERVICE])
    db.commit()
    db.execute("insert into tokens (session_id, service_id, token, origin, created) "
               "values (?, ?, ?, ?, datetime('now'))",
               [session_id, PROTECTED_IMAGE_SERVICE, token, origin])
    db.commit()


@app.route('/auth/post_login')
def post_login():
    """render a window-closing page"""
    return render_template('post_login.html')


@app.route('/auth/token')
def token_service():
    """Token service"""
    origin = request.args.get('origin')
    message_id = request.args.get('messageId')
    session_id = get_session_id()
    db_token = None
    print(f"looking for token for session {session_id}, service {PROTECTED_IMAGE_SERVICE}")
    if session_id:
        db_token = query_db('select * from tokens where session_id=? and service_id=?',
                            [session_id, PROTECTED_IMAGE_SERVICE], one=True)
    if db_token:
        print(f"found token {db_token['token']}")
        session_origin = db_token['origin']
        if origin == session_origin:
            token_object = {
                "accessToken": db_token['token'],
                "expiresIn": 600
            }
        else:
            print(f"session origin was {session_origin}")
            token_object = {
                "error": "invalidOrigin",
                "description": "Not the origin supplied at login"
            }
    else:
        token_object = {
            "error": "missingCredentials",
            "description": "to be filled out"
        }

    if message_id:
        # client is a browser
        token_object['messageId'] = message_id
        return render_template('token.html', token_object=json.dumps(token_object), origin=origin)

    # client isn't using postMessage
    return jsonify(token_object)


# Database to hold map of sessions to tokens issued
# you can't access the session object in an info.json request, because no credentials supplied


@app.route('/sessiontokens')
def view_session_tokens():
    """concession to admin dashboard"""
    db = get_db()
    db.execute("delete from tokens where created < date('now','-1 day')")
    db.commit()
    session_tokens = query_db('select * from tokens order by created desc')
    return render_template('session_tokens.html',
                           session_tokens=session_tokens,
                           user_session=get_session_id())


@app.route('/killsessions')
def kill_sessions():
    """Clear up all my current session tokens"""
    session_id = get_session_id()
    if session_id:
        db = get_db()
        db.execute("delete from tokens where session_id=?", [session_id])
        db.commit()
        for key in list(session.keys()):
            if key != 'session_id':
                session.pop(key, None)

    return redirect(url_for('view_session_tokens'))


def connect_db():
    """Connects to the specific database."""
    conn = sqlite3.connect(app.database)
    conn.row_factory = sqlite3.Row
    return conn


def get_db():
    """Opens a new database connection if there is none yet for the
    current application context, ensures the tokens table is present.
    """
    if not hasattr(g, 'sqlite_db'):
        g.sqlite_db = connect_db()
        g.sqlite_db.cursor().executescript("create table if not exists tokens ( "
                                           "session_id text not null, "
                                           "service_id text not null, "
                                           "token text not null, "
                                           "origin text not null, "
                                           "created text not null"
                                           ");")
    return g.sqlite_db


def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    if hasattr(g, 'sqlite_db'):
        g.sqlite_db.close()


if __name__ == '__main__':
    # app.run(ssl_context=app.config.get("SSL_CONTEXT", None))
    app.run()
