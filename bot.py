import os
import discord
import threading
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
from openai import OpenAI
from pymongo import MongoClient

# 1. Setup
load_dotenv()

# MongoDB Setup
mongo_uri = os.getenv("MONGO_URI")
history_collection = None 

try:
    db_client = MongoClient(mongo_uri)
    db_client.admin.command('ping')
    print("DEBUG: Successfully connected to MongoDB Atlas!")
    db = db_client["discord_bot_db"]
    history_collection = db["chat_history"]
except Exception as e:
    print(f"CRITICAL ERROR connecting to MongoDB: {e}")

# AI Setup
ai_client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

# Discord Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Database Helpers
def load_history(channel_id):
    if history_collection is not None:
        doc = history_collection.find_one({"channel_id": channel_id})
        return doc["history"] if doc else []
    return [] 

def save_history(channel_id, history):
    if history_collection is not None:
        result = history_collection.update_one(
            {"channel_id": channel_id},
            {"$set": {"history": history}},
            upsert=True
        )
        print(f"DEBUG: Save successful! Modified count: {result.modified_count}")

# Terminal Input Listener (The new feature!)
def terminal_input_listener(bot):
    channel_id = int(os.getenv("DISCORD_CHANNEL_ID"))
    print("Terminal input enabled. Type messages below to send to Discord.")
    while True:
        text = input("Terminal->Discord: ")
        if text:
            # We must use run_coroutine_threadsafe to talk to the async bot
            channel = bot.get_channel(channel_id)
            if channel:
                asyncio.run_coroutine_threadsafe(channel.send(text), bot.loop)
            else:
                print("Error: Could not find the channel. Check your DISCORD_CHANNEL_ID in .env")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    # Start the input thread when the bot is ready
    threading.Thread(target=terminal_input_listener, args=(bot,), daemon=True).start()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Process commands (if you add any later)
    await bot.process_commands(message)

    channel_id = str(message.channel.id)
    history = load_history(channel_id)
    
    # Keep only last 10 messages
    history.append({"role": "user", "content": message.content})
    history = history[-10:] 

    try:
        response = ai_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=history
        )
        ai_message = response.choices[0].message.content
        history.append({"role": "assistant", "content": ai_message})
        
        save_history(channel_id, history)
        
        await message.channel.send(ai_message)
    except Exception as e:
        print(f"ERROR: {e}")
        await message.channel.send("Error processing request.")

bot.run(os.getenv("DISCORD_TOKEN"))