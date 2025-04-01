import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import socket
from urllib.parse import urlparse
from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.engine import Engine
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))

# Database configuration
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    # Heroku/Render provides DATABASE_URL, but SQLAlchemy needs a different format
    url = urlparse(DATABASE_URL)
    if url.scheme == 'postgres':
        url = url._replace(scheme='postgresql')
    app.config['SQLALCHEMY_DATABASE_URI'] = url.geturl()
    logger.info(f"Using PostgreSQL database: {url.geturl()}")
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shopping.db'
    logger.info("Using SQLite database")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 1,
    'max_overflow': 0,
    'pool_timeout': 30,
    'pool_recycle': 1800,
    'pool_pre_ping': True,
    'pool_use_lifo': True
}

# Initialize SQLAlchemy and SocketIO
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', manage_session=False)

# Add event listener to handle connection cleanup
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, str) and dbapi_connection.startswith('sqlite'):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

class ShoppingList(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    access_key = db.Column(db.String(32), unique=True, nullable=False)
    items = db.relationship('ShoppingItem', backref='list', lazy=True)

class ShoppingItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(100), nullable=False)
    is_checked = db.Column(db.Boolean, default=False)
    list_id = db.Column(db.Integer, db.ForeignKey('shopping_list.id'), nullable=False)

def init_db():
    try:
        with app.app_context():
            db.create_all()
            logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise

# Initialize the database
init_db()

@app.route('/')
def index():
    access_key = request.args.get('key')
    if access_key:
        return redirect(url_for('shopping_list', key=access_key))
    
    if 'access_key' in session:
        return redirect(url_for('shopping_list'))
    return render_template('index.html')

@app.route('/create-list', methods=['GET', 'POST'])
def create_list():
    if request.method == 'POST':
        try:
            access_key = os.urandom(16).hex()
            new_list = ShoppingList(access_key=access_key)
            db.session.add(new_list)
            db.session.commit()
            
            session['access_key'] = access_key
            flash(f'Your shopping list has been created! Share this key with your friends: {access_key}')
            return redirect(url_for('shopping_list'))
        except Exception as e:
            logger.error(f"Error creating shopping list: {str(e)}")
            db.session.rollback()
            flash('An error occurred while creating your shopping list. Please try again.')
            return redirect(url_for('create_list'))
    
    return render_template('create_list.html')

@app.route('/join-list', methods=['GET', 'POST'])
def join_list():
    if request.method == 'POST':
        access_key = request.form['access_key']
        shopping_list = ShoppingList.query.filter_by(access_key=access_key).first()
        
        if shopping_list:
            session['access_key'] = access_key
            return redirect(url_for('shopping_list'))
        else:
            flash('Invalid access key')
    
    return render_template('join_list.html')

@app.route('/shopping-list')
def shopping_list():
    access_key = session.get('access_key') or request.args.get('key')
    if not access_key:
        return redirect(url_for('index'))
    
    shopping_list = ShoppingList.query.filter_by(access_key=access_key).first()
    if not shopping_list:
        session.pop('access_key', None)
        flash('Invalid access key')
        return redirect(url_for('index'))
    
    if access_key and 'access_key' not in session:
        session['access_key'] = access_key
    
    items = ShoppingItem.query.filter_by(list_id=shopping_list.id).all()
    return render_template('shopping_list.html', items=items, access_key=access_key)

@app.route('/add-item', methods=['POST'])
def add_item():
    if 'access_key' not in session:
        return redirect(url_for('index'))
    
    shopping_list = ShoppingList.query.filter_by(access_key=session['access_key']).first()
    if not shopping_list:
        return redirect(url_for('index'))
    
    item = request.form['item']
    new_item = ShoppingItem(item=item, list_id=shopping_list.id)
    db.session.add(new_item)
    db.session.commit()
    
    socketio.emit('item_added', {
        'id': new_item.id,
        'item': new_item.item,
        'is_checked': new_item.is_checked
    }, room=session['access_key'])
    
    return redirect(url_for('shopping_list'))

@app.route('/toggle-item/<int:item_id>')
def toggle_item(item_id):
    if 'access_key' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    shopping_list = ShoppingList.query.filter_by(access_key=session['access_key']).first()
    if not shopping_list:
        return jsonify({'error': 'Invalid access key'}), 401
    
    item = ShoppingItem.query.get_or_404(item_id)
    if item.list_id == shopping_list.id:
        item.is_checked = not item.is_checked
        db.session.commit()
        
        socketio.emit('item_updated', {
            'id': item.id,
            'is_checked': item.is_checked
        }, room=session['access_key'])
        
        return jsonify({'success': True, 'is_checked': item.is_checked})
    return jsonify({'error': 'Item not found'}), 404

@app.route('/leave-list')
def leave_list():
    if 'access_key' in session:
        leave_room(session['access_key'])
    session.pop('access_key', None)
    return redirect(url_for('index'))

@socketio.on('connect')
def handle_connect():
    if 'access_key' in session:
        join_room(session['access_key'])

@socketio.on('disconnect')
def handle_disconnect():
    if 'access_key' in session:
        leave_room(session['access_key'])

if __name__ == '__main__':
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"\nYou can access the application at:")
    print(f"Local: http://127.0.0.1:5000")
    print(f"Network: http://{local_ip}:5000")
    
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True) 