import json
import random
import os
from dotenv import load_dotenv
import openai
from anthropic import Anthropic
import google.generativeai as genai
from deepseek_ai import DeepSeekAI
import pprint

# Load environment variables
load_dotenv()

# Initialize API clients
openai.api_key = os.getenv("OPENAI_API_KEY")
anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
deepseek = DeepSeekAI(api_key=os.getenv("DEEPSEEK_API_KEY"))

translate_prompt = """
Översätt texten från svenska till engelska.

- Svara endast med den översatta texten, inga kommentarer eller förklaringar.
- Behåll länkar, BB-kod, emojis, citat exakt som de är.
- Om ett svenskt ord inte har en bra översättning på engelska, lämna det oförändrat.
"""

def translate_text(text, model_name):
    """Translate text using specified model"""
    try:
        if model_name == "gpt-4o":
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": translate_prompt},
                    {"role": "user", "content": text}
                ]
            )
            return {
                "text": response.choices[0].message.content,
                "tokens": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }
            
        elif model_name == "claude-3-7-sonnet-latest":
            response = anthropic.messages.create(
                model="claude-3-7-sonnet-latest",
                max_tokens=1000,
                system=translate_prompt,
                messages=[
                    {"role": "user", "content": text}
                ]
            )
            return {
                "text": response.content[0].text,
                "tokens": {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens
                }
            }
            
        elif model_name == "gemini-2.0-flash-exp":
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            response = model.generate_content(
                f"{translate_prompt}\n\n{text}"
            )
            tokens = {}
            try:
                tokens = {
                    "prompt_tokens": response.usage_metadata.prompt_token_count,
                    "completion_tokens": response.usage_metadata.candidates_token_count,
                    "total_tokens": response.usage_metadata.total_token_count
                }
            except AttributeError:
                print(f"Warning: Could not extract token usage from Gemini response")

            return {
                "text": response.text,
                "tokens": tokens
            }
            
        elif model_name == "deepseek-chat":
            response = deepseek.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": translate_prompt},
                    {"role": "user", "content": text}
                ]
            )
            result = response.result  # Extract actual result object
            tokens = {}
            try:
                tokens = {
                    "prompt_tokens": result.usage.prompt_tokens,
                    "completion_tokens": result.usage.completion_tokens,
                    "total_tokens": result.usage.total_tokens
                }
            except AttributeError:
                print("Warning: Could not extract token usage from DeepSeek result")

            return {
                "text": result.choices[0].message.content,
                "tokens": tokens
            }
            
        return {"text": "", "tokens": {}}
    except Exception as e:
        print(f"Error translating with {model_name}: {str(e)}")
        return {"text": "", "tokens": {}}

def process_threads():
    # Read the JSON files
    threads = []
    for filename in ['data/threads-random-a.json', 'data/threads-random-b.json', 'data/threads-random-c.json']:
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Only include threads with between 5 and 20 posts
                valid_threads = [thread for thread in data['threads'] if 5 <= len(thread['posts']) <= 20]
                threads.extend(valid_threads)
        except Exception as e:
            print(f"Error reading file {filename}: {str(e)}")
            continue
    
    if not threads:
        print("No valid threads found in the data files!")
        return
    
    print(f"Found {len(threads)} threads with 5-20 posts")
    
    # Select 10 random threads
    num_threads = min(10, len(threads))
    selected_threads = random.sample(threads, num_threads)
    
    # Models to use with their exact names
    models = [
        "gpt-4o",
        "claude-3-7-sonnet-latest",
        "gemini-2.0-flash-exp",
        "deepseek-chat"
    ]
    
    # Load existing translations if file exists
    existing_translations = []
    try:
        with open('translated_threads.json', 'r', encoding='utf-8') as f:
            existing_translations = json.load(f)
    except FileNotFoundError:
        print("No existing translations file found, starting fresh")
    except json.JSONDecodeError:
        print("Error reading existing translations file, starting fresh")
    
    # Get set of already translated thread IDs
    translated_ids = {thread["id"] for thread in existing_translations}
    
    # Process each thread
    translated_threads = []
    for i, thread in enumerate(selected_threads, 1):
        # Skip if thread is already translated
        if thread["id"] in translated_ids:
            print(f"\nSkipping thread {i} of {num_threads} (Thread ID: {thread['id']}) - already translated")
            continue
            
        print(f"\nProcessing thread {i} of {num_threads} (Thread ID: {thread['id']}, Posts: {len(thread['posts'])})...")
        print(f"Thread date: {thread['last_post_date']}")
        
        translated_thread = {
            "id": thread["id"],
            "title": thread["title"],
            "title_english": {},
            "post_date": thread["post_date"],
            "last_post_date": thread["last_post_date"],
            "forum_id": thread["forum_id"],
            "forum_title": thread["forum_title"],
            "posts": []
        }
        
        # Translate thread title
        print(f"Translating thread title...")
        for model in models:
            result = translate_text(thread["title"], model)
            translated_thread["title_english"][model] = {
                "text": result["text"],
                "tokens": result["tokens"]
            }
        
        # Process posts
        for j, post in enumerate(thread["posts"], 1):
            print(f"Processing post {j} of {len(thread['posts'])}...")
            translated_post = {
                "id": post["id"],
                "position": post["position"],
                "post_date": post["post_date"],
                "user_id": post["user_id"],
                "username": post["username"],
                "message": post["message"],
                "message_english": {}
            }
            
            # Translate message
            for model in models:
                result = translate_text(post["message"], model)
                translated_post["message_english"][model] = {
                    "text": result["text"],
                    "tokens": result["tokens"]
                }
            
            translated_thread["posts"].append(translated_post)
        
        translated_threads.append(translated_thread)
        
        # Combine existing translations with new ones and save
        all_translations = existing_translations + translated_threads
        with open('translated_threads.json', 'w', encoding='utf-8') as f:
            json.dump(all_translations, f, ensure_ascii=False, indent=2)
            print(f"Progress saved to translated_threads.json")

if __name__ == "__main__":
    process_threads() 