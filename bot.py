import os
import re
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient, events
import asyncio

# Use environment variables for credentials
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")

# Session file will be stored as 'session.session' in Railway environment
client = TelegramClient('session', api_id, api_hash)

default_group_name = "🔒 X-Force Group 🔒"
ALLOWED_CHAT_ID = -1002214482286  # Only allow /scrape in this chat

# Original regex patterns for quick line checks
line_patterns = [
    r'(\d{16})\D+(\d{2})\D+(\d{2})\D+(\d{3})',
    r'(\d{16})\D+(\d{2})\D+(\d{4})\D+(\d{3})',
    r'(\d{15})\D+(\d{2})\D+(\d{2})\D+(\d{4})',
    r'(\d{15})\D+(\d{2})\D+(\d{4})\D+(\d{3})',
]

# Multiline pattern for complex blocks
multiline_pattern = re.compile(r'''
    (?P<card>(?:\d[\d\s\-]{13,18}\d))   # Card number with optional spaces/dashes
    .*?                                 # non-greedy any chars (incl newlines)
    (?:EXPIRE:|Expiry|exp|exp\.?)?      # optional expiry label
    [\s:\|]*                            # optional separators
    (?P<month>0[1-9]|1[0-2])            # month 01-12
    /?                                  # optional slash
    (?P<year>\d{2}|\d{4})               # year 2 or 4 digits
    .*?                                 # non-greedy any chars
    (?:CVV:|CVC:|cvv|cvc)?              # optional cvv label
    [\s:\|]*                            # optional separators
    (?P<cvv>\d{3,4})                    # cvv 3 or 4 digits
''', re.IGNORECASE | re.DOTALL | re.VERBOSE)

def extract_digits(text):
    # Try line patterns first
    for line in text.splitlines():
        for pattern in line_patterns:
            match = re.search(pattern, line)
            if match:
                return '|'.join(match.groups())
    # Fallback to multiline pattern
    match = multiline_pattern.search(text)
    if match:
        card = re.sub(r'[\s\-]', '', match.group('card'))
        return f"{card}|{match.group('month')}|{match.group('year')}|{match.group('cvv')}"
    return None

async def get_group_by_name(name):
    async for dialog in client.iter_dialogs():
        if dialog.is_group and dialog.name == name:
            return dialog.entity
    return None

@client.on(events.NewMessage(pattern=r'/scrape(?:\s+(\d+))?(?:\s+(\S+))?'))
async def handler(event):
    # Restrict command usage
    if event.chat_id != ALLOWED_CHAT_ID:
        return

    hours_str = event.pattern_match.group(1)
    chat_arg = event.pattern_match.group(2)

    try:
        hours = int(hours_str) if hours_str else 24
    except ValueError:
        await event.respond("Please provide a valid number of hours, e.g., `/scrape 5`")
        return

    group = None

    if chat_arg:
        if "joinchat/" in chat_arg:
            from telethon.tl.functions.messages import ImportChatInviteRequest
            import re as _re

            async def join_private_invite_link(link):
                invite_hash_match = _re.search(r'joinchat/([a-zA-Z0-9_-]+)', link)
                if not invite_hash_match:
                    return None
                invite_hash = invite_hash_match.group(1)
                try:
                    chat = await client(ImportChatInviteRequest(invite_hash))
                    if hasattr(chat, 'chats') and chat.chats:
                        return chat.chats[0]
                    else:
                        return await client.get_entity(chat.chat_id if hasattr(chat, 'chat_id') else chat.chat.id)
                except Exception:
                    return None

            group = await join_private_invite_link(chat_arg)
            if not group:
                await event.respond("Failed to join the private invite link. Please check the link.")
                return
        else:
            try:
                group = await client.get_entity(chat_arg)
            except Exception:
                group = await get_group_by_name(chat_arg)
            if not group:
                await event.respond(f"Could not find a chat matching '{chat_arg}'. Using default group.")
                group = await get_group_by_name(default_group_name)
    else:
        group = await get_group_by_name(default_group_name)

    if not group:
        await event.respond(f"Default group '{default_group_name}' not found.")
        return

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    found_cards = []

    async for message in client.iter_messages(group):
        if message.date < since:
            break
        if message.text:
            digits = extract_digits(message.text)
            if digits:
                found_cards.append(digits)

    if found_cards:
        filename = 'found_cards.txt'
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('\n'.join(found_cards))

        await event.respond(f"Scraping done. Found {len(found_cards)} card(s) in the last {hours} hour(s) from {group.title}. Sending file...")
        await client.send_file(event.chat_id, filename)
        os.remove(filename)
    else:
        await event.respond(f"No cards found in the last {hours} hour(s) from {group.title}.")

async def main():
    await client.start()
    print("Bot is up and running...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
