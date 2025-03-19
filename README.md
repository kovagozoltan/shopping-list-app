# Shopping List App

A real-time collaborative shopping list application built with Flask and Socket.IO.

## Features

- Create and share shopping lists with unique access keys
- Real-time updates using WebSocket
- Mobile-friendly interface
- Easy sharing via URL or access key
- Persistent storage with SQLite/PostgreSQL

## Local Development

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the application:
   ```bash
   python app.py
   ```
5. Open your browser and navigate to `http://localhost:5000`

## Deployment

The application is configured to work with Render. To deploy:

1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Set the following environment variables:
   - `SECRET_KEY`: A random string for session security
   - `DATABASE_URL`: Your PostgreSQL database URL (provided by Render)

## Usage

1. Create a new shopping list or join an existing one using an access key
2. Add items to your list
3. Check off items as you buy them
4. Share the access key or URL with others to collaborate
5. All changes are synchronized in real-time

## Technologies Used

- Flask
- Flask-SQLAlchemy
- Flask-SocketIO
- SQLite/PostgreSQL
- Bootstrap 5
- Socket.IO 