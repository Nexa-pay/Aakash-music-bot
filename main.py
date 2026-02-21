import os
import logging
import asyncio
from typing import Optional
from datetime import datetime

import yt_dlp
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables")

# Download options for yt-dlp
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'outtmpl': 'downloads/%(title)s.%(ext)s',
    'quiet': True,
    'no_warnings': True,
}

# Search function using YouTube
async def search_youtube(query: str):
    """Search YouTube for the query and return first result"""
    ydl = yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True})
    try:
        info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
        return {
            'title': info['title'],
            'duration': info.get('duration', 0),
            'url': info['webpage_url'],
            'thumbnail': info.get('thumbnail', '')
        }
    except Exception as e:
        logger.error(f"Search error: {e}")
        return None

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when /start is issued."""
    welcome_msg = (
        "🎵 Welcome to Music Bot!\n\n"
        "I can help you play music from YouTube.\n\n"
        "Commands:\n"
        "/play [song name] - Play a song\n"
        "/help - Show this help message"
    )
    await update.message.reply_text(welcome_msg)

# Help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message."""
    help_msg = (
        "How to use the bot:\n\n"
        "1. Send /play [song name] to search and play a song\n"
        "2. Choose from the search results\n"
        "3. The bot will send you the audio file\n\n"
        "You can also just send me a song name directly!"
    )
    await update.message.reply_text(help_msg)

# Play command
async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /play command"""
    # Get the search query
    query = ' '.join(context.args) if context.args else None
    
    if not query:
        await update.message.reply_text(
            "Please provide a song name!\n"
            "Example: /play never gonna give you up"
        )
        return
    
    # Send searching message
    searching_msg = await update.message.reply_text(f"🔍 Searching for: {query}")
    
    # Search YouTube
    result = await search_youtube(query)
    
    if result:
        # Create inline keyboard with options
        keyboard = [
            [InlineKeyboardButton("🎵 Download & Send", callback_data=f"download_{result['url']}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Format duration
        minutes = result['duration'] // 60
        seconds = result['duration'] % 60
        duration_str = f"{minutes}:{seconds:02d}"
        
        # Send result
        await searching_msg.delete()
        await update.message.reply_text(
            f"🎵 Found: {result['title']}\n"
            f"⏱️ Duration: {duration_str}\n\n"
            f"Click below to download:",
            reply_markup=reply_markup
        )
    else:
        await searching_msg.edit_text("❌ No results found. Try another search!")

# Handle callback queries (button clicks)
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Operation cancelled.")
        return
    
    if query.data.startswith("download_"):
        url = query.data.replace("download_", "")
        
        # Update message to show downloading
        await query.edit_message_text("⬇️ Downloading audio... Please wait.")
        
        try:
            # Download audio
            audio_file = await download_audio(url)
            
            if audio_file:
                # Send audio file
                with open(audio_file, 'rb') as audio:
                    await context.bot.send_audio(
                        chat_id=update.effective_chat.id,
                        audio=audio,
                        title=os.path.basename(audio_file).replace('.mp3', ''),
                        performer="Music Bot"
                    )
                
                # Clean up - delete the file after sending
                os.remove(audio_file)
                await query.edit_message_text("✅ Audio sent successfully!")
            else:
                await query.edit_message_text("❌ Failed to download audio. Please try again.")
                
        except Exception as e:
            logger.error(f"Download error: {e}")
            await query.edit_message_text("❌ An error occurred while downloading.")

async def download_audio(url: str) -> Optional[str]:
    """Download audio from YouTube URL"""
    # Create downloads directory if it doesn't exist
    os.makedirs('downloads', exist_ok=True)
    
    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # Change extension to .mp3 (since we convert to mp3)
            filename = filename.rsplit('.', 1)[0] + '.mp3'
            
            if os.path.exists(filename):
                return filename
            return None
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None

# Handle direct messages (without command)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages that are not commands"""
    if update.message.text and not update.message.text.startswith('/'):
        # Treat as search query
        context.args = [update.message.text]
        await play(update, context)

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Start the bot"""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("play", play))
    
    # Add callback query handler for buttons
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add message handler for non-command messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Add error handler
    application.add_error_handler(error_handler)

    # Start the bot
    print("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()