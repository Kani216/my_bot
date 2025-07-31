from flask import Flask, request, jsonify
from flask_cors import CORS
import bot  # Import your backend code

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests for front-end

@app.route('/chat', methods=['POST'])
def chat_endpoint():
    data = request.get_json()
    message = data.get('message', '')
    if message.lower() == 'reset':
        response = bot.reset()
    else:
        response = bot.chat(message)
    return jsonify({'response': response})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)