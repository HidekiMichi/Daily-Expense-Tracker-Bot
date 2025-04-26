import discord
from discord.ext import commands
import aiosqlite
import datetime
import matplotlib.pyplot as plt
import io
import os
from fpdf import FPDF

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)



TOKEN = os.getenv('TOKEN')
  # Replace this with your bot token

CATEGORY_KEYWORDS = {
    "food": ["lunch", "dinner", "breakfast", "restaurant", "kfc", "dominos", "burger", "pizza", "McDonald's","Snacks"],
    "transport": ["uber", "taxi", "train", "bus", "fuel", "petrol", "MTR", "mtr","Mtr", "Metro"],
    "groceries": ["supermarket", "groceries", "vegetables", "fruits", "store"],
    "entertainment": ["netflix", "cinema", "movie", "concert", "game", "pubg"],
    "shopping": ["amazon", "flipkart", "clothes", "shopping", "electronics"]
}

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
    await ctx.send(f"Added ₹{amount} under **{detected_category}** ({description})")

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
        category_totals[category] = category_totals.get(category, 0) + amount
    categories = list(category_totals.keys())
    amounts = list(category_totals.values())
    plt.figure(figsize=(6,6))
    plt.pie(amounts, labels=categories, autopct='%1.1f%%', startangle=140)
    plt.title(f"Expenses Breakdown - {now.strftime('%B %Y')}")
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    file = discord.File(fp=buf, filename='report.png')
    await ctx.send(file=file)
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
        pdf.cell(0, 10, txt=f"{date} | ₹{amount} | {category} | {description}", ln=True)
        total += amount
    pdf.ln(10)
    pdf.set_font("Arial", 'B', size=12)
    pdf.cell(0, 10, txt=f"Total Spent: ₹{total:.2f}", ln=True)
    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    await ctx.send(file=discord.File(fp=buf, filename="expense_report.pdf"))

bot.run(TOKEN)