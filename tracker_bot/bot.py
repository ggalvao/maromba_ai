import os
import json
import re
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
)
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TrainingTemplateManager:
    """Manages training plan templates for users"""
    
    def __init__(self, templates_file: str = "templates.json"):
        self.templates_file = templates_file
        self.templates = self._load_templates()
    
    def _load_templates(self) -> Dict:
        """Load templates from JSON file"""
        try:
            with open(self.templates_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def _save_templates(self):
        """Save templates to JSON file"""
        with open(self.templates_file, 'w') as f:
            json.dump(self.templates, f, indent=2)
    
    def get_user_templates(self, user_id: str) -> Dict:
        """Get all templates for a user"""
        return self.templates.get(user_id, {})
    
    def get_template(self, user_id: str, template_name: str) -> Optional[Dict]:
        """Get specific template for a user"""
        user_templates = self.get_user_templates(user_id)
        return user_templates.get(template_name.lower())
    
    def add_template(self, user_id: str, template_name: str, exercises: Dict[str, str]):
        """Add or update a template for a user"""
        if user_id not in self.templates:
            self.templates[user_id] = {}
        
        self.templates[user_id][template_name.lower()] = {
            'name': template_name,
            'exercises': exercises,
            'created_date': datetime.now().isoformat()
        }
        self._save_templates()
    
    def delete_template(self, user_id: str, template_name: str) -> bool:
        """Delete a template for a user"""
        user_templates = self.templates.get(user_id, {})
        if template_name.lower() in user_templates:
            del self.templates[user_id][template_name.lower()]
            self._save_templates()
            return True
        return False
    
    def list_templates(self, user_id: str) -> List[str]:
        """List all template names for a user"""
        user_templates = self.get_user_templates(user_id)
        return [template['name'] for template in user_templates.values()]

class GoogleSheetsManager:
    """Manages Google Sheets integration for workout data storage"""
    
    def __init__(self, credentials_file: str, spreadsheet_name: str = "Weight Training Tracker", spreadsheet_id: str = None, impersonate_user: str = None):
        self.credentials_file = credentials_file
        self.spreadsheet_name = spreadsheet_name
        self.spreadsheet_id = spreadsheet_id
        self.impersonate_user = impersonate_user
        self.gc = None
        self.sheet = None
        self._setup_sheets()
    
    def _setup_sheets(self):
        """Setup Google Sheets connection"""
        try:
            # Define the scope
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
            
            # Load credentials
            creds = Credentials.from_service_account_file(
                self.credentials_file, scopes=scope
            )
            
            # If impersonating a user, delegate credentials
            if self.impersonate_user:
                creds = creds.with_subject(self.impersonate_user)
                logger.info(f"Using domain-wide delegation to impersonate: {self.impersonate_user}")
            
            self.gc = gspread.authorize(creds)
            
            # Open spreadsheet by ID if provided, otherwise by name
            try:
                if self.spreadsheet_id:
                    self.sheet = self.gc.open_by_key(self.spreadsheet_id).sheet1
                    logger.info(f"Opened spreadsheet by ID: {self.spreadsheet_id}")
                else:
                    self.sheet = self.gc.open(self.spreadsheet_name).sheet1
                    logger.info(f"Opened spreadsheet by name: {self.spreadsheet_name}")
            except gspread.SpreadsheetNotFound:
                if self.spreadsheet_id:
                    raise ValueError(f"Spreadsheet with ID {self.spreadsheet_id} not found or not shared with service account")
                
                # Try to create new spreadsheet (will likely fail due to quota)
                logger.info("Attempting to create new spreadsheet...")
                spreadsheet = self.gc.create(self.spreadsheet_name)
                self.sheet = spreadsheet.sheet1
                
                # Setup headers
                headers = [
                    "Date", "Time", "User ID", "Username", "Template Used",
                    "Exercise", "Weight", "Reps", "Sets", "RIR/RPE", "Comment"
                ]
                self.sheet.append_row(headers)
                
                logger.info(f"Created new spreadsheet: {self.spreadsheet_name}")
        
        except Exception as e:
            logger.error(f"Error setting up Google Sheets: {e}")
            raise
    
    def log_workout_entry(self, user_id: str, username: str, template_name: str, 
                         exercise: str, weight: float, reps: int, sets: int, 
                         rir_rpe: str = "", comment: str = ""):
        """Log a single workout entry to Google Sheets"""
        try:
            now = datetime.now()
            row = [
                now.strftime("%Y-%m-%d"),
                now.strftime("%H:%M:%S"),
                user_id,
                username,
                template_name,
                exercise,
                weight,
                reps,
                sets,
                rir_rpe,
                comment
            ]
            self.sheet.append_row(row)
            logger.info(f"Logged workout entry for user {username}: {exercise}")
        
        except Exception as e:
            logger.error(f"Error logging workout entry: {e}")
            raise

class WorkoutParser:
    """Parses workout input from users"""
    
    @staticmethod
    def parse_workout_line(line: str) -> Optional[Tuple[str, float, int, int, str, str]]:
        """
        Parse a single workout line
        Format: "exercise_ref. weight x reps x sets [RIR/RPE] [comment]"
        Returns: (exercise_ref, weight, reps, sets, rir_rpe, comment)
        """
        line = line.strip()
        if not line:
            return None
        
        # Pattern: number/name. weight x reps x sets [optional RIR/RPE] [optional comment]
        pattern = r'^([^.]+)\.\s*(\d+(?:\.\d+)?)\s*x\s*(\d+)\s*x\s*(\d+)\s*(.*)$'
        match = re.match(pattern, line, re.IGNORECASE)
        
        if not match:
            return None
        
        exercise_ref = match.group(1).strip()
        weight = float(match.group(2))
        reps = int(match.group(3))
        sets = int(match.group(4))
        remainder = match.group(5).strip()
        
        # Parse RIR/RPE and comment from remainder
        rir_rpe = ""
        comment = remainder
        
        # Look for RIR or RPE patterns
        rir_pattern = r'(?:RIR|rir)\s*(\d+(?:\.\d+)?)'
        rpe_pattern = r'(?:RPE|rpe)\s*(\d+(?:\.\d+)?)'
        
        rir_match = re.search(rir_pattern, remainder, re.IGNORECASE)
        rpe_match = re.search(rpe_pattern, remainder, re.IGNORECASE)
        
        if rir_match:
            rir_rpe = f"RIR {rir_match.group(1)}"
            comment = re.sub(rir_pattern, '', remainder, flags=re.IGNORECASE).strip()
        elif rpe_match:
            rir_rpe = f"RPE {rpe_match.group(1)}"
            comment = re.sub(rpe_pattern, '', remainder, flags=re.IGNORECASE).strip()
        
        return exercise_ref, weight, reps, sets, rir_rpe, comment

class WeightTrainingBot:
    """Main bot class"""
    
    def __init__(self, bot_token: str, google_credentials_file: str = None, spreadsheet_id: str = None, impersonate_user: str = None):
        self.bot_token = bot_token
        self.template_manager = TrainingTemplateManager()
        self.sheets_manager = None
        if google_credentials_file and os.path.exists(google_credentials_file):
            try:
                self.sheets_manager = GoogleSheetsManager(
                    google_credentials_file, 
                    spreadsheet_id=spreadsheet_id,
                    impersonate_user=impersonate_user
                )
                logger.info("Google Sheets integration enabled")
            except Exception as e:
                logger.warning(f"Google Sheets setup failed: {e}")
                logger.info("Running without Google Sheets integration")
        else:
            logger.info("Running without Google Sheets integration")
        self.app = None
        self.current_workouts = {}  # Track ongoing workouts per user
    
    def create_app(self):
        """Create and configure the Telegram application"""
        self.app = Application.builder().token(self.bot_token).build()
        
        # Add handlers
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("templates", self.list_templates_command))
        self.app.add_handler(CommandHandler("addtemplate", self.add_template_command))
        self.app.add_handler(CommandHandler("deletetemplate", self.delete_template_command))
        self.app.add_handler(CommandHandler("workout", self.start_workout_command))
        self.app.add_handler(CommandHandler("endworkout", self.end_workout_command))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        return self.app
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_message = """
🏋️ Welcome to Weight Training Tracker!

This bot helps you track your workouts using templates for fast data entry.

**Quick Start:**
1. Create templates: `/addtemplate`
2. Start workout: `/workout TemplateName`
3. Log exercises: `1. 80x8x3 RIR 2`
4. End workout: `/endworkout`

**Commands:**
• `/help` - Show detailed help
• `/templates` - List your templates
• `/addtemplate` - Create new template
• `/workout` - Start logging workout
• `/endworkout` - Finish current workout

**Input Format:**
`exercise_number. weight x reps x sets [RIR/RPE] [comment]`

Example: `1. 80x8x3 RIR 2 Felt strong`
        """
        await update.message.reply_text(welcome_message)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_message = """
🏋️ **Weight Training Tracker Help**

**Template System:**
Templates map numbers to exercises for fast input during workouts.

**Creating Templates:**
1. Use `/addtemplate TemplateName`
2. Enter exercises one per line: `1. Exercise Name`
3. Send "done" when finished

Example template creation:
```
/addtemplate Push Day A
1. Bench Press
2. Overhead Press  
3. Incline Dumbbell Press
4. Lateral Raises
done
```

**Using Templates:**
1. Start workout: `/workout Push Day A`
2. Log exercises: `1. 80x8x3 RIR 2`
3. Continue logging...
4. End: `/endworkout`

**Input Format Details:**
`number. weight x reps x sets [RIR/RPE] [comment]`

**Examples:**
• `1. 80x8x3` - Basic entry
• `1. 80x8x3 RIR 2` - With RIR
• `1. 80x8x3 RPE 8` - With RPE  
• `1. 80x8x3 RIR 2 Felt strong` - With comment
• `1. 80x8x3 Easy set` - Just comment

**Commands:**
• `/templates` - List your templates
• `/addtemplate Name` - Create template
• `/deletetemplate Name` - Delete template
• `/workout Name` - Start workout with template
• `/endworkout` - Finish current workout
        """
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    async def list_templates_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /templates command"""
        user_id = str(update.effective_user.id)
        templates = self.template_manager.list_templates(user_id)
        
        if not templates:
            await update.message.reply_text("You don't have any templates yet. Create one with /addtemplate")
        else:
            message = "📋 **Your Templates:**\n\n"
            for template_name in templates:
                template = self.template_manager.get_template(user_id, template_name)
                message += f"**{template_name}:**\n"
                for num, exercise in template['exercises'].items():
                    message += f"  {num}. {exercise}\n"
                message += "\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
    
    async def add_template_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /addtemplate command"""
        if not context.args:
            await update.message.reply_text(
                "Please provide a template name: `/addtemplate TemplateName`",
                parse_mode='Markdown'
            )
            return
        
        template_name = " ".join(context.args)
        user_id = str(update.effective_user.id)
        
        # Start template creation process
        context.user_data['creating_template'] = {
            'name': template_name,
            'exercises': {}
        }
        
        await update.message.reply_text(
            f"Creating template: **{template_name}**\n\n"
            "Enter exercises one per line in format: `number. Exercise Name`\n"
            "Example: `1. Bench Press`\n\n"
            "Send `done` when finished.",
            parse_mode='Markdown'
        )
    
    async def delete_template_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /deletetemplate command"""
        if not context.args:
            await update.message.reply_text(
                "Please provide a template name: `/deletetemplate TemplateName`",
                parse_mode='Markdown'
            )
            return
        
        template_name = " ".join(context.args)
        user_id = str(update.effective_user.id)
        
        if self.template_manager.delete_template(user_id, template_name):
            await update.message.reply_text(f"✅ Deleted template: {template_name}")
        else:
            await update.message.reply_text(f"❌ Template '{template_name}' not found")
    
    async def start_workout_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /workout command"""
        if not context.args:
            # Show available templates
            user_id = str(update.effective_user.id)
            templates = self.template_manager.list_templates(user_id)
            
            if not templates:
                await update.message.reply_text(
                    "You don't have any templates. Create one first with `/addtemplate`",
                    parse_mode='Markdown'
                )
                return
            
            keyboard = []
            for template in templates:
                keyboard.append([InlineKeyboardButton(template, callback_data=f"workout_{template}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Select a template for your workout:",
                reply_markup=reply_markup
            )
            return
        
        template_name = " ".join(context.args)
        await self._start_workout_with_template(update, template_name)
    
    async def _start_workout_with_template(self, update: Update, template_name: str):
        """Start workout with specified template"""
        user_id = str(update.effective_user.id)
        template = self.template_manager.get_template(user_id, template_name)
        
        if not template:
            await update.message.reply_text(f"❌ Template '{template_name}' not found")
            return
        
        # Store current workout
        self.current_workouts[user_id] = {
            'template': template,
            'start_time': datetime.now(),
            'entries': []
        }
        
        # Show template exercises
        message = f"🏋️ Started workout: **{template['name']}**\n\n**Exercises:**\n"
        for num, exercise in template['exercises'].items():
            message += f"{num}. {exercise}\n"
        
        message += "\n📝 Log exercises using: `number. weight x reps x sets [RIR/RPE] [comment]`\n"
        message += "Example: `1. 80x8x3 RIR 2`\n\n"
        message += "Use `/endworkout` when finished."
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def end_workout_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /endworkout command"""
        user_id = str(update.effective_user.id)
        
        if user_id not in self.current_workouts:
            await update.message.reply_text("❌ No active workout to end")
            return
        
        workout = self.current_workouts[user_id]
        duration = datetime.now() - workout['start_time']
        entry_count = len(workout['entries'])
        
        del self.current_workouts[user_id]
        
        message = f"✅ **Workout Completed!**\n\n"
        message += f"Template: {workout['template']['name']}\n"
        message += f"Duration: {str(duration).split('.')[0]}\n"
        message += f"Exercises logged: {entry_count}\n\n"
        message += "Great work! 💪"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks"""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("workout_"):
            template_name = query.data[8:]  # Remove "workout_" prefix
            await self._start_workout_with_template(query, template_name)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages"""
        user_id = str(update.effective_user.id)
        text = update.message.text.strip()
        
        # Check if user is creating a template
        if 'creating_template' in context.user_data:
            await self._handle_template_creation(update, context, text)
            return
        
        # Check if user has an active workout
        if user_id in self.current_workouts:
            await self._handle_workout_entry(update, text)
            return
        
        # General message when no active session
        await update.message.reply_text(
            "Use `/help` for instructions or `/workout` to start logging exercises.",
            parse_mode='Markdown'
        )
    
    async def _handle_template_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """Handle template creation input"""
        if text.lower() == 'done':
            # Finish template creation
            template_data = context.user_data['creating_template']
            user_id = str(update.effective_user.id)
            
            if not template_data['exercises']:
                await update.message.reply_text("❌ Template must have at least one exercise")
                return
            
            self.template_manager.add_template(
                user_id, 
                template_data['name'], 
                template_data['exercises']
            )
            
            del context.user_data['creating_template']
            
            await update.message.reply_text(
                f"✅ Created template: **{template_data['name']}** with {len(template_data['exercises'])} exercises",
                parse_mode='Markdown'
            )
            return
        
        # Parse exercise entry: "number. Exercise Name"
        pattern = r'^(\d+)\.\s*(.+)$'
        match = re.match(pattern, text)
        
        if not match:
            await update.message.reply_text(
                "❌ Invalid format. Use: `number. Exercise Name`\n"
                "Example: `1. Bench Press`\n"
                "Send `done` when finished.",
                parse_mode='Markdown'
            )
            return
        
        number = match.group(1)
        exercise = match.group(2).strip()
        
        context.user_data['creating_template']['exercises'][number] = exercise
        
        await update.message.reply_text(
            f"✅ Added: {number}. {exercise}\n"
            "Continue adding exercises or send `done` to finish."
        )
    
    async def _handle_workout_entry(self, update: Update, text: str):
        """Handle workout entry input"""
        user_id = str(update.effective_user.id)
        username = update.effective_user.username or update.effective_user.first_name
        
        parsed = WorkoutParser.parse_workout_line(text)
        if not parsed:
            await update.message.reply_text(
                "❌ Invalid format. Use: `number. weight x reps x sets [RIR/RPE] [comment]`\n"
                "Example: `1. 80x8x3 RIR 2`",
                parse_mode='Markdown'
            )
            return
        
        exercise_ref, weight, reps, sets, rir_rpe, comment = parsed
        
        # Get exercise name from template
        workout = self.current_workouts[user_id]
        template = workout['template']
        
        if exercise_ref not in template['exercises']:
            available = ", ".join(template['exercises'].keys())
            await update.message.reply_text(
                f"❌ Exercise '{exercise_ref}' not found in template.\n"
                f"Available: {available}"
            )
            return
        
        exercise_name = template['exercises'][exercise_ref]
        
        # Log to Google Sheets if available
        sheets_logged = False
        if self.sheets_manager:
            try:
                self.sheets_manager.log_workout_entry(
                    user_id, username, template['name'],
                    exercise_name, weight, reps, sets, rir_rpe, comment
                )
                sheets_logged = True
            except Exception as e:
                logger.error(f"Error logging workout entry to sheets: {e}")
        
        # Store in current workout
        workout['entries'].append({
            'exercise': exercise_name,
            'weight': weight,
            'reps': reps,
            'sets': sets,
            'rir_rpe': rir_rpe,
            'comment': comment
        })
        
        # Confirmation message
        message = f"✅ Logged: **{exercise_name}**\n"
        message += f"Weight: {weight}kg, Reps: {reps}, Sets: {sets}"
        if rir_rpe:
            message += f", {rir_rpe}"
        if comment:
            message += f"\nComment: {comment}"
        
        if not sheets_logged:
            message += "\n⚠️ Note: Google Sheets logging unavailable"
        
        await update.message.reply_text(message, parse_mode='Markdown')

def main():
    """Main function to run the bot"""
    # Load environment variables from .env file
    load_dotenv()
    
    # Environment variables
    BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    GOOGLE_CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE', 'google_credentials.json')
    SPREADSHEET_ID = os.getenv('GOOGLE_SPREADSHEET_ID')
    IMPERSONATE_USER = os.getenv('GOOGLE_IMPERSONATE_USER')
    
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
    
    # Create and run bot
    bot = WeightTrainingBot(BOT_TOKEN, GOOGLE_CREDENTIALS_FILE, SPREADSHEET_ID, IMPERSONATE_USER)
    app = bot.create_app()
    
    logger.info("Starting Weight Training Tracker Bot...")
    app.run_polling()

if __name__ == '__main__':
    main()