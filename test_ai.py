import ollama

print("Czekam na odpowiedź od AI...")

# Wysyłamy wiadomość do modelu
response = ollama.chat(model='llama3.1', messages=[
    {
        'role': 'user',
        'content': 'uzywasz mojego cpu czy gpu?',
    },
])

# Wyświetlamy to, co odpowiedziało AI
print("-" * 30)
print(response['message']['content'])
print("-" * 30)