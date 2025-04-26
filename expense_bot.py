# ----------------------------------------
# imports
import discord
from discord.ext import commands
import aiosqlite
import datetime
import matplotlib.pyplot as plt
import io
import os
from fpdf import FPDF
from flask import Flask
from threading import Thread

# ----------------------------------------
# flask server to keep port open
app = Flask('')

@app.route('/')
def home():
    return "Hello. I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ----------------------------------------
# discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

TOKEN = os.getenv('TOKEN')

CATEGORY_KEYWORDS = {
    "food": ["lunch", "Food", "food","dinner", "breakfast", "restaurant", "kfc", "dominos", "burger", "pizza", "McDonald's", "Snacks"],
    "transport": ["uber", "taxi", "train", "bus", "fuel", "petrol", "MTR", "mtr", "Mtr", "Metro"],
    "groceries": ["supermarket", "groceries", "vegetables", "fruits", "store"],
    "entertainment": ["netflix", "cinema", "movie", "concert", "game", "pubg"],
    "shopping": ["amazon", "flipkart", "clothes", "shopping", "electronics"],
    "miscellaneous": ["misc", "other", "miscellaneous", "random", "various"],
    "Octopus Card": ["octopus", "octopus card", "octopuscard", "Octopuscard", "Octopus Card", "Octopus"],
}

# ----------------------------------------
# discord bot events

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    async with aiosqlite.connect('expenses.db') as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                category TEXT,
                description TEXT,
                date TEXT
            )
        ''')
        await db.commit()

@bot.command()
async def add(ctx, amount: float, *, description: str):
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    desc_lower = description.lower()
    detected_category = "others"

    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in desc_lower for keyword in keywords):
            detected_category = category
            break

    async with aiosqlite.connect('expenses.db') as db:
        await db.execute('''
            INSERT INTO expenses (user_id, amount, category, description, date)
            VALUES (?, ?, ?, ?, ?)
        ''', (ctx.author.id, amount, detected_category, description, date))
        await db.commit()

        # Get the ID of the newly added expense
        cursor = await db.execute('SELECT last_insert_rowid()')
        row = await cursor.fetchone()
        expense_id = row[0]

    await ctx.send(
        f"✅ Added ₹{amount} under **{detected_category}** (`{description}`) — ID: `{expense_id}`"
    )

@bot.command()
async def remove(ctx, expense_id: int):
    async with aiosqlite.connect('expenses.db') as db:
        cursor = await db.execute('SELECT user_id FROM expenses WHERE id = ?', (expense_id,))
        row = await cursor.fetchone()
        if not row:
            await ctx.send(f"No expense found with ID {expense_id}.")
            return
        if row[0] != ctx.author.id:
            await ctx.send("You can only remove your own expenses.")
            return
        await db.execute('DELETE FROM expenses WHERE id = ?', (expense_id,))
        await db.commit()
    await ctx.send(f"Expense with ID {expense_id} has been removed.")

@bot.command()
async def list(ctx):
    async with aiosqlite.connect('expenses.db') as db:
        cursor = await db.execute(
            'SELECT id, amount, category, description, date FROM expenses WHERE user_id = ? ORDER BY date DESC',
            (ctx.author.id,)
        )
        rows = await cursor.fetchall()

    if not rows:
        await ctx.send("You don't have any expenses saved yet.")
        return

    # Build the list as a message
    message_lines = ["📋 **Your Expenses:**"]
    for row in rows:
        expense_id, amount, category, description, date = row
        message_lines.append(
            f"• ID: `{expense_id}` | ₹{amount} | {category} | \"{description}\" on {date}"
        )

    # Discord message limit: 2000 characters
    message = "\n".join(message_lines)
    if len(message) > 2000:
        await ctx.send("Too many expenses to display! Try filtering or exporting.")
    else:
        await ctx.send(message)

@bot.command()
async def balance(ctx):
    now = datetime.datetime.now()
    month = now.strftime("%Y-%m")
    async with aiosqlite.connect('expenses.db') as db:
        cursor = await db.execute('''
            SELECT SUM(amount) FROM expenses
            WHERE user_id = ? AND date LIKE ?
        ''', (ctx.author.id, f'{month}%'))
        result = await cursor.fetchone()
    total_spent = result[0] if result[0] else 0
    await ctx.send(f"💰 **Total spent in {now.strftime('%B %Y')}: ₹{total_spent:.2f}**")

@bot.command()
async def report(ctx):
    now = datetime.datetime.now()
    month = now.strftime("%Y-%m")
    
    async with aiosqlite.connect('expenses.db') as db:
        cursor = await db.execute('''
            SELECT amount, category FROM expenses
            WHERE user_id = ? AND date LIKE ?
        ''', (ctx.author.id, f'{month}%'))
        rows = await cursor.fetchall()

    if not rows:
        await ctx.send("No expenses found for this month.")
        return

    category_totals = {}
    for amount, category in rows:
        category_totals[category] = category_totals.get(category, 0) + float(amount)

    # Ensure we pass actual lists, not coroutines
    categories = list(category_totals.keys())
    amounts = list(category_totals.values())

    # DEBUG: Print to console to verify types (optional)
    # print(f"Categories: {categories} ({type(categories)}), Amounts: {amounts} ({type(amounts)})")

    # Create the pie chart
    plt.figure(figsize=(6, 6))
    plt.pie(amounts, labels=categories, autopct='%1.1f%%', startangle=140)
    plt.title(f"Expenses Breakdown - {now.strftime('%B %Y')}")
    plt.tight_layout()

    # Save and send image
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    file = discord.File(fp=buf, filename='report.png')
    await ctx.send(file=file)

    # Send the summary
    total = sum(amounts)
    summary = "\n".join([f"**{cat}**: ₹{amt:.2f}" for cat, amt in category_totals.items()])
    await ctx.send(f"📅 **Monthly Summary for {now.strftime('%B %Y')}**\n\n{summary}\n\n**Total**: ₹{total:.2f}")

@bot.command()
async def pdf_report(ctx):
    now = datetime.datetime.now()
    month = now.strftime("%Y-%m")
    async with aiosqlite.connect('expenses.db') as db:
        cursor = await db.execute('''
            SELECT amount, category, description, date FROM expenses
            WHERE user_id = ? AND date LIKE ?
        ''', (ctx.author.id, f'{month}%'))
        rows = await cursor.fetchall()
    if not rows:
        await ctx.send("No expenses found for this month.")
        return
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Monthly Expense Report - {now.strftime('%B %Y')}", ln=True, align='C')
    pdf.ln(10)
    total = 0
    for amount, category, description, date in rows:
        pdf.cell(0, 10, txt=f"{date} | HKD{amount} | {category} | {description}", ln=True)
        total += amount
    pdf.ln(10)
    pdf.set_font("Arial", 'B', size=12)
    pdf.cell(0, 10, txt=f"Total Spent: HKD{total:.2f}", ln=True)
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    buf = io.BytesIO(pdf_bytes)
    buf.seek(0)
    await ctx.send(file=discord.File(fp=buf, filename="expense_report.pdf"))

# ----------------------------------------
# start the web server + bot
keep_alive()
bot.run(TOKEN)
