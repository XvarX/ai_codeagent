def _parse_room_prefix(content: str) -> tuple[str, dict | None]:
    """If content starts with a [Room: ...] prefix, strip it and return roomInfo.

    Returns (clean_content, roomInfo | None).
    """
    import re
    # Pattern 1: [Room: name ← agent]\ntext  or  [Room: ← agent]\ntext
    m = re.match(r'^\[Room:\s*([^←→|\n]*?)\s*←\s*([^\]]*?)\]\n', content)
    if m:
        room_name = m.group(1).strip()
        sender = m.group(2).strip()
        return content[m.end():], {
            "roomId": "", "roomName": room_name,
            "senderName": sender, "senderId": "",
            "direction": "in",
        }
    # Pattern 2: [Room: name | From: agent | To: xxx]\ntext (relay format, optional To)
    m = re.match(
        r'^\[Room:\s*([^|←→\n]*?)\s*\|\s*From:\s*([^|\]]*?)(?:\s*\|\s*To:\s*([^\]]*))?\]\n',
        content)
    if m:
        room_name = m.group(1).strip()
        sender_raw = m.group(2).strip()
        sender = re.sub(r'\s*\(id:[^)]*\)\s*$', '', sender_raw).strip()
        info = {
            "roomId": "", "roomName": room_name,
            "senderName": sender, "senderId": "",
            "direction": "in",
        }
        reply_to = (m.group(3) or "").strip()
        if reply_to:
            info["replyTo"] = reply_to
        return content[m.end():], info
    # Pattern 3: [Room: name → All]\ntext (user sent to room)
    m = re.match(r'^\[Room:\s*([^←→|\n]*?)\s*→\s*[^\]]*\]\n', content)
    if m:
        room_name = m.group(1).strip()
        return content[m.end():], {
            "roomId": "", "roomName": room_name,
            "direction": "out",
        }
    # Pattern 4: [Room: name | Members: ... | From: 用户]\ntext (user room message relay)
    m = re.match(
        r'^\[Room:\s*([^|←→\n]*?)\s*\|\s*Members:.*?\|\s*From:\s*([^\]]*?)\]\n',
        content)
    if m:
        room_name = m.group(1).strip()
        sender = m.group(2).strip()
        return content[m.end():], {
            "roomId": "", "roomName": room_name,
            "senderName": sender, "senderId": "",
            "direction": "in" if sender != "用户" else "out",
        }
    return content, None
