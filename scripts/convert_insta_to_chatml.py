#!/usr/bin/env python3
"""
Instagram raw export → SFT-ready conversation JSONL (single pipeline)
VERBOSE LOGGING VERSION - FIXED for conversations starting with assistant
"""

import glob
import json
import os
import re
from typing import List, Dict, Optional, Tuple

# ============================================================================
# CONFIGURATION
# ============================================================================

RAW_INBOX = "data/raw-insta/your_instagram_activity/messages/inbox"
OUTPUT = "data/insta-sft.jsonl"
STATS_FILE = "data/insta-sft-stats.json"
MY_NAME = "Saurya"

MIN_CONVERSATION_LENGTH = 2
BURST_MERGE_WINDOW_MS = 90_000

ROLE_MAP = {"friend": "user", "saurya": "assistant"}

# Debug mode - set to False for production
DEBUG_MODE = False
VERBOSE = False  # Set to False to reduce noise

# ============================================================================
# SYSTEM MESSAGE FILTERING - FIXED TO ACTUALLY FILTER
# ============================================================================

# Exact matches for system messages to filter out
SYSTEM_EXACT = {
    "this message has been deleted",
    "this message was deleted",
    "message deleted",
    "you started a video chat",
    "you started an audio call",
    "video chat ended",
    "audio call ended",
    "you missed a video chat",
    "you missed an audio call",
    "you missed a voice call",
    "on liked",
    "sent an attachment",
    "sent a photo",
    "sent a video",
    "sent a gif",
    "sent a sticker",
    "sent a voice message",
    "sent a link",
    "sent a location",
    "shared a story",
    "shared a post",
    "shared a reel",
    "shared a video",
    "shared a photo",
    "liked a message",
    "reacted to your message",
    "reacted to a message",
}

# Patterns for system messages
SYSTEM_PATTERNS = [
    r"^sent an attachment\.?$",
    r"^sent a (voice message|link|location|photo|video|gif|sticker)\.?$",
    r"^shared a (story|post|reel|video|photo)\.?$",
    r"^reacted .{1,20} to (your|a) message\.?$",
    r"^liked (your|a) message\.?$",
    r"^(video|voice|audio) call,?\s+\d",
    r"^(started|ended|missed|declined) (a |the )?(video |voice |audio )?call\.?$",
    r"^(created|named|changed|removed|added|left|joined) (the |a )?group",
    r"^removed .+ from (the |a )?group",
    r"^added .+ to (the |a )?group",
    r"^you can now (message|call) each other",
    r"^you can now see (info|information)",
]
SYSTEM_RE = re.compile("|".join(SYSTEM_PATTERNS), re.IGNORECASE)


def fix_unicode_string(s: str) -> str:
    """Fix mojibake by re-encoding as latin1 and decoding as utf-8."""
    if not isinstance(s, str):
        return s
    
    try:
        if any(ord(c) > 0x7F for c in s):
            fixed = s.encode('latin1').decode('utf-8')
            if '\ufffd' not in fixed and fixed != s:
                return fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    
    return s


def is_system_message(content: str) -> bool:
    """
    True if this is Instagram metadata that should be filtered out.
    """
    stripped = content.strip()
    if not stripped:
        return True
    
    lower = stripped.lower()
    
    # Check exact matches
    if lower in SYSTEM_EXACT:
        return True
    
    # Check for "[anything] sent an attachment"
    if re.search(r".+ sent an attachment\.?$", lower):
        return True
    
    # Check for "[anything] shared a story"
    if re.search(r".+ shared a story\.?$", lower):
        return True
    
    # Check for "[anything] liked a message"
    if re.search(r".+ liked a message\.?$", lower):
        return True
    
    # Check for "[anything] reacted to [your/a] message"
    if re.search(r".+ reacted .+ to (your|a) message\.?$", lower):
        return True
    
    # Check for reaction patterns like "Reacted ❤️ to your message"
    if "reacted" in lower and "to your message" in lower:
        return True
    
    # Check for "sent a [media type]"
    media_types = ["voice message", "link", "location", "photo", "video", "gif", "sticker"]
    for media in media_types:
        if re.search(rf".+ sent a {re.escape(media)}\.?$", lower):
            return True
    
    # Check patterns
    if SYSTEM_RE.search(stripped):
        return True
    
    return False

def message_to_content(msg: dict) -> Optional[str]:
    """Extract text or return None for media-only messages."""
    content = msg.get("content")
    
    if content is None:
        share = msg.get("share")
        if share and isinstance(share, dict):
            link = share.get("link")
            share_text = share.get("share_text")
            if link:
                content = link
            elif share_text:
                content = share_text
        
        # For media-only messages with no text, filter them out completely
        if msg.get("photos") or msg.get("videos") or msg.get("audio_files") or msg.get("gifs") or msg.get("sticker"):
            return None
    
    if not content:
        return None
    
    # Remove "Reacted X to your message" type content that might still be in content field
    content_lower = content.lower()
    if "reacted" in content_lower and "to your message" in content_lower:
        return None
    
    return fix_unicode_string(content.strip())


# ============================================================================
# THREAD LOADING
# ============================================================================

def get_thread_info(thread_dir: str) -> Tuple[str, str]:
    """Extract folder name and other participants from thread directory."""
    folder_name = os.path.basename(thread_dir)
    
    participants = []
    for f in glob.glob(os.path.join(thread_dir, "message_*.json")):
        try:
            with open(f, encoding='utf-8') as fp:
                data = json.load(fp)
                for p in data.get("participants", []):
                    name = p.get("name", "")
                    if name and name.lower() != MY_NAME.lower():
                        participants.append(name)
        except:
            continue
        if participants:
            break
    
    other_person = participants[0] if participants else "unknown"
    return folder_name, other_person


def load_thread(thread_dir: str) -> Tuple[Optional[List], List[Dict]]:
    """Load all message_N.json files in a thread with proper UTF-8."""
    files = sorted(
        glob.glob(os.path.join(thread_dir, "message_*.json")),
        key=lambda p: int(re.search(r"message_(\d+)\.json$", p).group(1)),
    )
    if not files:
        if VERBOSE:
            print(f"  No message files found in {thread_dir}")
        return None, []

    participants = None
    messages = []

    for filepath in files:
        try:
            with open(filepath, encoding='utf-8') as f:
                data = json.load(f)
            
            if participants is None:
                participants = data.get("participants", [])
                for p in participants:
                    if "name" in p:
                        p["name"] = fix_unicode_string(p["name"])
            
            thread_msgs = data.get("messages", [])
            for m in thread_msgs:
                if "content" in m and m["content"]:
                    m["content"] = fix_unicode_string(m["content"])
                if "sender_name" in m:
                    m["sender_name"] = fix_unicode_string(m["sender_name"])
            
            messages.extend(thread_msgs)
            if VERBOSE:
                print(f"  Loaded {len(thread_msgs)} messages from {os.path.basename(filepath)}")
        except Exception as e:
            print(f"  Warning: Error parsing {filepath}: {e}")
            continue

    return participants, messages


# ============================================================================
# CONVERSATION PROCESSING
# ============================================================================

def merge_bursts(conv: List[Dict]) -> List[Dict]:
    """Merge same-role messages within 90 seconds."""
    if not conv:
        return conv

    merged = [conv[0].copy()]
    CONJUNCTION_STARTS = ("but ", "and ", "actually ", "wait ", "no ", "oh ", "btw ", "also ")
    merges_done = 0

    for msg in conv[1:]:
        prev = merged[-1]
        same_role = msg["role"] == prev["role"]
        time_delta = msg.get("timestamp_ms", 0) - prev.get("timestamp_ms", 0)

        starts_with_conj = msg["content"].lstrip().lower().startswith(CONJUNCTION_STARTS)
        combined_len = len(prev["content"].split()) + len(msg["content"].split())

        if same_role and time_delta <= BURST_MERGE_WINDOW_MS and not starts_with_conj and combined_len <= 40:
            prev["content"] += "\n" + msg["content"]
            prev["timestamp_ms"] = msg.get("timestamp_ms", prev["timestamp_ms"])
            merges_done += 1
        else:
            merged.append(msg.copy())

    if VERBOSE and merges_done > 0:
        print(f"    Merged {merges_done} burst messages")
    
    return merged


def deduplicate_conversations(conv: List[Dict]) -> List[Dict]:
    """Remove duplicate consecutive messages."""
    if not conv:
        return conv
    
    deduped = []
    seen = set()
    removed = 0
    
    for msg in conv:
        key = (msg["role"], msg["content"])
        
        if key in seen:
            removed += 1
            continue
        
        if deduped and deduped[-1]["role"] != msg["role"]:
            seen.clear()
        
        deduped.append(msg)
        seen.add(key)
        
        if len(seen) > 10:
            seen.clear()
    
    if VERBOSE and removed > 0:
        print(f"    Removed {removed} duplicate messages")
    
    return deduped


def convert_to_sft_format(messages: List[Dict]) -> List[Dict]:
    """Convert raw messages to SFT format (user/assistant roles)."""
    converted = []
    
    for msg in messages:
        role_raw = msg.get("role", "").strip().lower()
        content = msg.get("content", "").strip()

        if role_raw not in ROLE_MAP:
            if VERBOSE:
                print(f"    Skipping unknown role: {role_raw}")
            continue
        if not content:
            continue

        converted.append({"role": ROLE_MAP[role_raw], "content": content})
    
    # Remove consecutive duplicates
    if converted:
        deduped = [converted[0]]
        removed = 0
        for msg in converted[1:]:
            last = deduped[-1]
            if msg["role"] == last["role"] and msg["content"] == last["content"]:
                removed += 1
                continue
            deduped.append(msg)
        if VERBOSE and removed > 0:
            print(f"    Removed {removed} duplicate messages in SFT conversion")
        converted = deduped
    
    return converted


def fix_alternation(messages: List[Dict]) -> List[Dict]:
    """Fix non-alternating sequences by merging consecutive same-role messages."""
    if not messages:
        return messages
    
    fixed = []
    merges = 0
    for msg in messages:
        if fixed and fixed[-1]["role"] == msg["role"]:
            fixed[-1]["content"] += "\n" + msg["content"]
            merges += 1
        else:
            fixed.append(msg.copy())
    
    if VERBOSE and merges > 0:
        print(f"    Fixed alternation: merged {merges} same-role messages")
    
    return fixed


def ensure_valid_start(messages: List[Dict]) -> List[Dict]:
    """
    Ensure conversation starts properly for SFT training.
    SFT format requires first message to be from user (the person asking for help).
    If first message is from assistant (Saurya), we need to check if we can still use it.
    """
    if not messages:
        return []
    
    # If first message is already from user, great
    if messages[0]["role"] == "user":
        return messages
    
    # Keep conversations that start with assistant
    return messages


# ============================================================================
# STATISTICS
# ============================================================================

class Stats:
    def __init__(self):
        self.total_conversations = 0
        self.total_messages = 0
        self.skipped_group = 0
        self.skipped_no_me = 0
        self.skipped_short = 0
        self.skipped_bad_start = 0
        self.skipped_bad_alternation = 0
        self.system_dropped = 0
        self.empty_dropped = 0
        self.burst_merges = 0
        self.deduplicated = 0
        self.alternation_fixed = 0
        self.conversations_starting_with_assistant = 0
        self.by_person = {}
        self.threads_processed = 0

    def print_summary(self):
        print(f"\n{'='*70}")
        print(f"INSTAGRAM → SFT PIPELINE COMPLETE")
        print(f"{'='*70}")
        print(f"Threads processed: {self.threads_processed}")
        print(f"Conversations saved: {self.total_conversations}")
        print(f"Total messages (after processing): {self.total_messages}")
        print(f"\nSkipped:")
        print(f"  - Group chats: {self.skipped_group}")
        print(f"  - You not in chat: {self.skipped_no_me}")
        print(f"  - Too short (<{MIN_CONVERSATION_LENGTH} turns): {self.skipped_short}")
        print(f"  - Bad alternation (unfixable): {self.skipped_bad_alternation}")
        print(f"\nFiltered:")
        print(f"  - System messages: {self.system_dropped}")
        print(f"  - Empty/media messages: {self.empty_dropped}")
        print(f"\nTransformations:")
        print(f"  - Burst merges: {self.burst_merges}")
        print(f"  - Duplicates removed: {self.deduplicated}")
        print(f"  - Alternation fixed: {self.alternation_fixed}")
        print(f"  - Conversations starting with assistant: {self.conversations_starting_with_assistant}")
        
        if self.by_person:
            print(f"\nTop 10 participants by conversation count:")
            for person, count in sorted(self.by_person.items(), key=lambda x: -x[1])[:10]:
                print(f"  - {person}: {count} conversations")
        
        print(f"{'='*70}\n")


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def main():
    print("="*70)
    print("STARTING INSTAGRAM → SFT PIPELINE")
    print("="*70)
    print(f"Input directory: {RAW_INBOX}")
    print(f"Output file: {OUTPUT}")
    print(f"Your name: {MY_NAME}")
    print(f"Debug mode: {DEBUG_MODE}")
    print(f"Verbose logging: {VERBOSE}")
    print("="*70 + "\n")

    # Create output directory if needed
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    
    # Verify input directory exists
    if not os.path.exists(RAW_INBOX):
        print(f"ERROR: Input directory not found: {RAW_INBOX}")
        print("Please check the path and run again.")
        return
    
    stats = Stats()

    # Find all thread directories
    print("Scanning for thread directories...")
    thread_dirs = set()
    for root, dirs, files in os.walk(RAW_INBOX):
        rel = os.path.relpath(root, RAW_INBOX)
        # Only look at top-level directories (one level deep)
        if rel != "." and len(rel.split(os.sep)) > 1:
            continue
        if any(f.startswith("message_") and f.endswith(".json") for f in files):
            thread_dirs.add(root)

    print(f"Found {len(thread_dirs)} thread directories\n")

    if len(thread_dirs) == 0:
        print("ERROR: No thread directories found!")
        print(f"Please check that {RAW_INBOX} contains folders with message_*.json files")
        return

    with open(OUTPUT, "w", encoding='utf-8') as out_f:
        for idx, thread_dir in enumerate(sorted(thread_dirs)):
            folder_name = os.path.basename(thread_dir)
            
            if VERBOSE:
                print(f"\n[{idx+1}/{len(thread_dirs)}] Processing: {folder_name}")
            
            participants, raw_messages = load_thread(thread_dir)
            stats.threads_processed += 1

            if not participants:
                if VERBOSE:
                    print(f"  No participants found, skipping")
                stats.skipped_no_me += 1
                continue

            names = [p.get("name", "").lower() for p in participants]

            if MY_NAME.lower() not in names:
                if VERBOSE:
                    print(f"  {MY_NAME} not in participants, skipping")
                stats.skipped_no_me += 1
                continue

            if len(names) != 2:
                if VERBOSE:
                    print(f"  Group chat ({len(names)} participants), skipping")
                stats.skipped_group += 1
                continue

            # Get debug info
            other_person = None
            for p in participants:
                if p.get("name", "").lower() != MY_NAME.lower():
                    other_person = p.get("name", "unknown")
                    break
            
            if VERBOSE:
                print(f"  Conversation with: {other_person}")
                print(f"  Raw messages found: {len(raw_messages)}")
            
            if other_person:
                stats.by_person[other_person] = stats.by_person.get(other_person, 0) + 1

            if len(raw_messages) == 0:
                if VERBOSE:
                    print(f"  No messages found, skipping")
                continue

            # Sort by timestamp
            raw_messages.sort(key=lambda m: m.get("timestamp_ms", 0))
            
            if VERBOSE:
                print(f"  Messages after sorting: {len(raw_messages)}")

            # Build conversation with proper roles
            conv = []
            filtered_system = 0
            filtered_empty = 0
            
            for m in raw_messages:
                sender = (m.get("sender_name") or "").lower()
                role = "saurya" if sender == MY_NAME.lower() else "friend"
                content = message_to_content(m)

                if content is None:
                    filtered_empty += 1
                    stats.empty_dropped += 1
                    continue

                if is_system_message(content):
                    filtered_system += 1
                    stats.system_dropped += 1
                    continue

                conv.append({
                    "role": role,
                    "content": content,
                    "timestamp_ms": m.get("timestamp_ms"),
                })
            
            if VERBOSE:
                print(f"  After filtering: {len(conv)} messages (filtered {filtered_system} system, {filtered_empty} empty/media)")
            
            if len(conv) == 0:
                if VERBOSE:
                    print(f"  No messages left after filtering, skipping")
                continue
            
            # Deduplicate
            original_len = len(conv)
            conv = deduplicate_conversations(conv)
            stats.deduplicated += (original_len - len(conv))
            
            if VERBOSE:
                print(f"  After deduplication: {len(conv)} messages")
            
            # Merge bursts
            conv = merge_bursts(conv)
            
            if VERBOSE:
                print(f"  After burst merging: {len(conv)} messages")

            # Check if first message is from assistant
            if conv and conv[0]["role"] == "saurya":
                stats.conversations_starting_with_assistant += 1

            # Convert to SFT format (friend→user, saurya→assistant)
            conv = convert_to_sft_format(conv)
            if not conv or len(conv) < MIN_CONVERSATION_LENGTH:
                if VERBOSE:
                    print(f"  Too short ({len(conv) if conv else 0} messages, need {MIN_CONVERSATION_LENGTH}), skipping")
                stats.skipped_short += 1
                continue
            
            if VERBOSE:
                print(f"  After SFT format conversion: {len(conv)} messages")

            # Fix alternation issues
            original_len = len(conv)
            conv = fix_alternation(conv)
            if len(conv) != original_len:
                stats.alternation_fixed += 1
            
            if VERBOSE:
                print(f"  After alternation fix: {len(conv)} messages")

            # Ensure valid start (don't trim, just check)
            if not conv:
                if VERBOSE:
                    print(f"  No messages after validation, skipping")
                continue
            
            # For SFT, we want at least one user-assistant pair
            if len(conv) < 2:
                if VERBOSE:
                    print(f"  Too short after validation, skipping")
                stats.skipped_short += 1
                continue
            
            # Check if we have at least one user and one assistant
            has_user = any(msg["role"] == "user" for msg in conv)
            has_assistant = any(msg["role"] == "assistant" for msg in conv)
            
            if not has_user or not has_assistant:
                if VERBOSE:
                    print(f"  Missing required roles (user: {has_user}, assistant: {has_assistant}), skipping")
                stats.skipped_bad_alternation += 1
                continue

            stats.total_messages += len(conv)
            
            # Build output object
            output_obj = {"messages": conv}
            
            # Add debug info
            if DEBUG_MODE:
                output_obj["_debug_source"] = {
                    "folder": folder_name,
                    "other_participant": other_person,
                    "starts_with_assistant": conv[0]["role"] == "assistant"
                }
            
            out_f.write(json.dumps(output_obj, ensure_ascii=False) + "\n")
            stats.total_conversations += 1
            
            if VERBOSE:
                print(f"  ✓ SAVED: {len(conv)} messages from {other_person} (starts with {conv[0]['role']})")

    stats.print_summary()
    
    # Save stats to file
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            "conversations_saved": stats.total_conversations,
            "total_messages": stats.total_messages,
            "skipped_group": stats.skipped_group,
            "skipped_no_me": stats.skipped_no_me,
            "skipped_short": stats.skipped_short,
            "skipped_bad_alternation": stats.skipped_bad_alternation,
            "system_messages_filtered": stats.system_dropped,
            "empty_media_filtered": stats.empty_dropped,
            "burst_merges": stats.burst_merges,
            "duplicates_removed": stats.deduplicated,
            "alternation_fixed": stats.alternation_fixed,
            "conversations_starting_with_assistant": stats.conversations_starting_with_assistant,
            "threads_processed": stats.threads_processed,
            "by_participant": stats.by_person,
        }, f, indent=2)
    
    print(f"Stats saved to: {STATS_FILE}")
    print(f"Output saved to: {OUTPUT}")
    
    # Show sample output
    if stats.total_conversations > 0:
        print("\n" + "="*70)
        print("SAMPLE OUTPUT (first conversation):")
        print("="*70)
        try:
            with open(OUTPUT, "r", encoding='utf-8') as f:
                first_line = f.readline()
                if first_line:
                    sample = json.loads(first_line)
                    if DEBUG_MODE and "_debug_source" in sample:
                        src = sample["_debug_source"]
                        print(f"Source: {src['folder']} (with {src['other_participant']})")
                        print(f"Starts with assistant: {src.get('starts_with_assistant', False)}")
                        print("-" * 50)
                    for i, msg in enumerate(sample["messages"][:6]):
                        role = msg["role"]
                        content = msg["content"][:80] + "..." if len(msg["content"]) > 80 else msg["content"]
                        print(f"{i+1}. {role}: {content}")
                    if len(sample["messages"]) > 6:
                        print(f"... and {len(sample['messages']) - 6} more messages")
        except Exception as e:
            print(f"Error reading sample: {e}")
        print("="*70)
    else:
        print("\n" + "!"*70)
        print("NO CONVERSATIONS WERE SAVED!")
        print("!"*70)
        print("\nPossible issues to check:")
        print("1. The RAW_INBOX path is correct")
        print("2. MY_NAME matches exactly how your name appears in the export")
        print("3. The export contains 1-on-1 conversations (not just group chats)")
        print("4. Messages have content (not just media)")
        print("5. Check the stats above for what was skipped")
        print("!"*70)


if __name__ == "__main__":
    main()
