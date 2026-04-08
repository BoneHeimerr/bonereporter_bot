import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import gspread
from google.oauth2.service_account import Credentials
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ──
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1szZNoVc8f9YsJK1d-N2AJSMjPlw9W5e_MY5IxJ5EkYM")
SHEET_NAME = os.environ.get("SHEET_NAME", "Daily Report")

# ── Google Sheets auth ──
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

def get_sheet():
    creds_json = os.environ["GOOGLE_CREDENTIALS"]
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    return sh.worksheet(SHEET_NAME)

# ── Account mapping ──
# Each account: (name_row, header_row, data_start, data_end, total_row, col_offset)
# col_offset: 0=A-F, 7=H-M, 14=O-T
ACCOUNTS = {
    "001": {"label": "jackpotdaily 001 (STEVEN)", "row_start": 5, "row_end": 18, "total": 19, "col": 0},
    "002": {"label": "jackpotdaily 002 (MK)",     "row_start": 5, "row_end": 18, "total": 19, "col": 7},
    "002s":{"label": "jackpotdaily 002 (STEVEN)", "row_start": 5, "row_end": 18, "total": 19, "col": 14},
    "003": {"label": "jackpotdaily 003 (STEVEN)", "row_start": 24,"row_end": 37, "total": 38, "col": 7-7},
    "004": {"label": "jackpotdaily 004 (STEVEN)", "row_start": 24,"row_end": 37, "total": 38, "col": 7},
    "005": {"label": "jackpotdaily 005 (STEVEN)", "row_start": 24,"row_end": 37, "total": 38, "col": 14},
    "006": {"label": "jackpotdaily 006 (STEVEN)", "row_start": 43,"row_end": 56, "total": 57, "col": 0},
    "007": {"label": "jackpotdaily 007 (STEVEN)", "row_start": 43,"row_end": 56, "total": 57, "col": 7},
    "008": {"label": "jackpotdaily 008 (STEVEN)", "row_start": 43,"row_end": 56, "total": 57, "col": 14},
}

OVERALL = {"row_start": 62, "row_end": 75, "total": 76}


def parse_money(val):
    """Parse money values like '$2.936,62' or '$41,19' or '0' or '' or 'N/A'"""
    if not val or val == "N/A" or val == "-":
        return 0.0
    val = str(val).replace("$", "").replace(" ", "").strip()
    # Google Sheets with locale: dots as thousands, comma as decimal
    # e.g. "2.936,62" -> 2936.62
    if "," in val and "." in val:
        val = val.replace(".", "").replace(",", ".")
    elif "," in val:
        val = val.replace(",", ".")
    return float(val)


def safe_int(val):
    if not val or val == "N/A" or val == "-":
        return 0
    return int(float(str(val).replace(",", ".")))


def get_account_data(ws, acct_key):
    """Fetch all rows for a single account."""
    acct = ACCOUNTS[acct_key]
    c = acct["col"]  # 0, 7, or 14
    rows = []
    for r in range(acct["row_start"], acct["row_end"] + 1):
        date_val = ws.cell(r, c + 1).value
        spend = parse_money(ws.cell(r, c + 2).value)
        ftds = safe_int(ws.cell(r, c + 3).value)
        cpa = ws.cell(r, c + 4).value or "N/A"
        regs = safe_int(ws.cell(r, c + 5).value)
        cpr = ws.cell(r, c + 6).value or "N/A"
        if spend > 0 or ftds > 0 or regs > 0:
            rows.append({"date": date_val, "spend": spend, "ftds": ftds, "cpa": cpa, "regs": regs, "cpr": cpr})
    # Totals
    tr = acct["total"]
    total = {
        "spend": parse_money(ws.cell(tr, c + 2).value),
        "ftds": safe_int(ws.cell(tr, c + 3).value),
        "cpa": ws.cell(tr, c + 4).value or "N/A",
        "regs": safe_int(ws.cell(tr, c + 5).value),
        "cpr": ws.cell(tr, c + 6).value or "N/A",
    }
    return acct["label"], rows, total


def get_overall_data(ws):
    """Fetch OVERALL section."""
    rows = []
    for r in range(OVERALL["row_start"], OVERALL["row_end"] + 1):
        date_val = ws.cell(r, 1).value
        spend = parse_money(ws.cell(r, 2).value)
        ftds = safe_int(ws.cell(r, 3).value)
        cpa = ws.cell(r, 4).value or "N/A"
        regs = safe_int(ws.cell(r, 5).value)
        cpr = ws.cell(r, 6).value or "N/A"
        if spend > 0 or ftds > 0 or regs > 0:
            rows.append({"date": date_val, "spend": spend, "ftds": ftds, "cpa": cpa, "regs": regs, "cpr": cpr})
    tr = OVERALL["total"]
    total = {
        "spend": parse_money(ws.cell(tr, 2).value),
        "ftds": safe_int(ws.cell(tr, 3).value),
        "cpa": ws.cell(tr, 4).value or "N/A",
        "regs": safe_int(ws.cell(tr, 5).value),
        "cpr": ws.cell(tr, 6).value or "N/A",
    }
    return rows, total


def fmt(val):
    if isinstance(val, float):
        return f"${val:,.2f}"
    return str(val)


# ── Commands ──

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🎰 *Jackpotdaily Report Bot*\n\n"
        "Available commands:\n\n"
        "📊 `/report` — Full overview of all accounts\n"
        "🔍 `/account 001` — Report for a specific account\n"
        "💰 `/cpa` — Overall CPA summary\n"
        "📝 `/cpr` — Overall CPR summary\n"
        "💵 `/spend` — Total spend per account\n"
        "📈 `/today` — Today's numbers across all accounts\n"
        "📋 `/accounts` — List all account IDs\n\n"
        "Account IDs: `001` `002` `002s` `003` `004` `005` `006` `007` `008`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def accounts_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["🗂 *Account List*\n"]
    for key, acct in ACCOUNTS.items():
        lines.append(f"• `{key}` → {acct['label']}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Fetching data...")
    try:
        ws = get_sheet()
        lines = ["📊 *JACKPOTDAILY — Full Report*\n"]

        for key in ACCOUNTS:
            label, rows, total = get_account_data(ws, key)
            lines.append(f"\n*{label}*")
            lines.append(f"  Spend: {fmt(total['spend'])} | FTDs: {total['ftds']} | CPA: {total['cpa']}")
            lines.append(f"  Regs: {total['regs']} | CPR: {total['cpr']}")

        _, ov_total = get_overall_data(ws)
        lines.append(f"\n🏆 *OVERALL TOTALS*")
        lines.append(f"  Spend: {fmt(ov_total['spend'])}")
        lines.append(f"  FTDs: {ov_total['ftds']} | CPA: {ov_total['cpa']}")
        lines.append(f"  Regs: {ov_total['regs']} | CPR: {ov_total['cpr']}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


async def account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/account 001`", parse_mode="Markdown")
        return
    key = context.args[0].lower()
    if key not in ACCOUNTS:
        await update.message.reply_text(f"❌ Unknown account `{key}`. Use `/accounts` to see the list.", parse_mode="Markdown")
        return

    await update.message.reply_text("⏳ Fetching data...")
    try:
        ws = get_sheet()
        label, rows, total = get_account_data(ws, key)
        lines = [f"🔍 *{label}*\n"]

        if rows:
            lines.append("```")
            lines.append(f"{'Date':<12} {'Spend':>10} {'FTDs':>5} {'Regs':>5}")
            lines.append("-" * 36)
            for r in rows:
                lines.append(f"{r['date']:<12} {fmt(r['spend']):>10} {r['ftds']:>5} {r['regs']:>5}")
            lines.append("-" * 36)
            lines.append(f"{'TOTAL':<12} {fmt(total['spend']):>10} {total['ftds']:>5} {total['regs']:>5}")
            lines.append("```")
        else:
            lines.append("No data with activity yet.")

        lines.append(f"\n💰 CPA: *{total['cpa']}*  |  📝 CPR: *{total['cpr']}*")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


async def cpa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Fetching data...")
    try:
        ws = get_sheet()
        lines = ["💰 *CPA Summary (All Accounts)*\n"]
        for key in ACCOUNTS:
            label, _, total = get_account_data(ws, key)
            short = label.split("(")[0].strip()
            lines.append(f"• {short} → *{total['cpa']}*  ({total['ftds']} FTDs)")

        _, ov_total = get_overall_data(ws)
        lines.append(f"\n🏆 *Overall CPA: {ov_total['cpa']}* ({ov_total['ftds']} total FTDs)")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cpr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Fetching data...")
    try:
        ws = get_sheet()
        lines = ["📝 *CPR Summary (All Accounts)*\n"]
        for key in ACCOUNTS:
            label, _, total = get_account_data(ws, key)
            short = label.split("(")[0].strip()
            lines.append(f"• {short} → *{total['cpr']}*  ({total['regs']} regs)")

        _, ov_total = get_overall_data(ws)
        lines.append(f"\n🏆 *Overall CPR: {ov_total['cpr']}* ({ov_total['regs']} total regs)")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def spend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Fetching data...")
    try:
        ws = get_sheet()
        lines = ["💵 *Spend Summary (All Accounts)*\n"]
        grand = 0
        for key in ACCOUNTS:
            label, _, total = get_account_data(ws, key)
            short = label.split("(")[0].strip()
            lines.append(f"• {short} → *{fmt(total['spend'])}*")
            grand += total["spend"]

        lines.append(f"\n🏆 *Total Spend: {fmt(grand)}*")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Fetching data...")
    try:
        ws = get_sheet()
        # Find the last row with data across all accounts
        lines = ["📈 *Latest Day With Data*\n"]
        _, ov_rows, ov_total = get_overall_data(ws)[0], None, None
        ov_rows, ov_total = get_overall_data(ws)

        if ov_rows:
            last = ov_rows[-1]
            lines.append(f"📅 Date: *{last['date']}*")
            lines.append(f"💵 Spend: *{fmt(last['spend'])}*")
            lines.append(f"🎯 FTDs: *{last['ftds']}*  |  CPA: *{last['cpa']}*")
            lines.append(f"📝 Regs: *{last['regs']}*  |  CPR: *{last['cpr']}*")

            lines.append(f"\n📊 *Breakdown by account:*")
            for key in ACCOUNTS:
                _, rows, _ = get_account_data(ws, key)
                matching = [r for r in rows if r["date"] == last["date"]]
                if matching:
                    m = matching[0]
                    short = ACCOUNTS[key]["label"].split("(")[0].strip()
                    lines.append(f"• {short}: {fmt(m['spend'])} | {m['ftds']} FTDs | {m['regs']} regs")
        else:
            lines.append("No data yet.")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("account", account))
    app.add_handler(CommandHandler("cpa", cpa))
    app.add_handler(CommandHandler("cpr", cpr))
    app.add_handler(CommandHandler("spend", spend))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("accounts", accounts_list))

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
