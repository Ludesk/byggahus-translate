import streamlit as st
import json
from pathlib import Path
import string
from pymongo import MongoClient
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Define the order of models and their display names
MODEL_ORDER = {
    'deepseek-chat': 1,  # Column 2
    'gemini-2.0-flash-exp': 2,  # Column 3
    'claude-3-7-sonnet-latest': 3,  # Column 4
    'gpt-4o': 4  # Column 5
}

MODEL_DISPLAY_NAMES = {
    'deepseek-chat': 'Model A',
    'gemini-2.0-flash-exp': 'Model B',
    'claude-3-7-sonnet-latest': 'Model C',
    'gpt-4o': 'Model D'
}

# MongoDB connection
@st.cache_resource
def get_mongo_client():
    # Try to get MongoDB URI from Streamlit secrets first
    try:
        mongo_uri = st.secrets["mongodb"]["uri"]
    except:
        # Fall back to environment variable for local development
        mongo_uri = os.getenv("MONGODB_URI")
    
    if not mongo_uri:
        st.error("MongoDB connection string not found. Please check your configuration.")
        return None
    
    try:
        return MongoClient(mongo_uri)
    except Exception as e:
        st.error(f"Failed to connect to MongoDB: {str(e)}")
        return None

@st.cache_resource
def get_db():
    client = get_mongo_client()
    if client:
        return client.get_database("translation_votes")
    return None

def initialize_votes_collection():
    db = get_db()
    if db is not None:
        if "votes" not in db.list_collection_names():
            db.create_collection("votes")
            db.votes.create_index([("thread_id", 1), ("post_id", 1)])

def save_vote(thread_id, post_id, selected_model, user_ip):
    db = get_db()
    if db is not None:
        vote = {
            "thread_id": thread_id,
            "post_id": post_id,
            "model": selected_model,
            "user_ip": user_ip,
            "timestamp": datetime.utcnow()
        }
        db.votes.insert_one(vote)

def get_vote_stats(thread_id, post_id):
    db = get_db()
    if db is not None:
        pipeline = [
            {"$match": {"thread_id": thread_id, "post_id": post_id}},
            {"$group": {
                "_id": "$model",
                "count": {"$sum": 1}
            }}
        ]
        results = list(db.votes.aggregate(pipeline))
        total = sum(result["count"] for result in results)
        return {result["_id"]: result["count"] for result in results}, total
    return {}, 0

# Load the translated threads
@st.cache_data
def load_threads():
    with open('translated_threads.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def get_translation_models(thread):
    """Get all unique translation models used in the thread and sort them according to MODEL_ORDER"""
    models = set()
    # Get models from title translations
    models.update(thread['title_english'].keys())
    # Get models from post translations
    for post in thread['posts']:
        models.update(post['message_english'].keys())
    # Sort models according to MODEL_ORDER
    return sorted(list(models), key=lambda x: MODEL_ORDER.get(x, 999))

def get_model_display_name(model):
    """Get the display name for a model (e.g., 'Model A')"""
    return MODEL_DISPLAY_NAMES.get(model, f"Unknown Model ({model})")

def get_actual_model_name(display_name):
    """Get the actual model name from the display name"""
    reverse_mapping = {v: k for k, v in MODEL_DISPLAY_NAMES.items()}
    return reverse_mapping.get(display_name, display_name)

def main():
    st.set_page_config(
        page_title="Forum Thread Translations",
        page_icon="🌐",
        layout="wide"
    )
    
    # Initialize MongoDB
    initialize_votes_collection()
    
    st.title("Forum Thread Translations")
    st.markdown("---")
    
    # Load threads
    threads = load_threads()
    
    # Create navigation
    thread_titles = [f"{thread['id']} - {thread['title']}" for thread in threads]
    selected_thread = st.selectbox(
        "Select a thread to view:",
        options=range(len(threads)),
        format_func=lambda x: thread_titles[x]
    )
    
    # Get the selected thread
    thread = threads[selected_thread]
    
    # Get all translation models used in this thread
    models = get_translation_models(thread)
    
    # Create columns for original and each translation model
    columns = st.columns(1 + len(models))
    
    # Display thread metadata
    with columns[0]:
        st.subheader("Original")
        st.markdown(f"**Title:** {thread['title']}")
    
    # Display title translations
    for i, model in enumerate(models, 1):
        with columns[i]:
            display_name = get_model_display_name(model)
            st.subheader(display_name)
            if model in thread['title_english']:
                st.markdown(f"**Title :** {thread['title_english'][model]['text']}")
    
    st.markdown("---")
    
    # Display posts
    for post in thread['posts']:
        if post['position'] == 0:
            st.markdown(f"### Fråga")
        else:
            st.markdown(f"### Svar {post['position']}")
        
        # Create columns for this post
        post_columns = st.columns(1 + len(models))
        
        # Original post
        with post_columns[0]:
            st.markdown("**Original Post**")
            st.markdown(f"**User:** {post['username']}")
            st.markdown("---")
            st.markdown(post['message'])
            
            # Voting for original post
            st.markdown("---")
            st.markdown("**Vote for this post**")
            vote_options = [get_model_display_name(model) for model in models]
            selected_vote = st.radio(
                "Which translation is best?",
                options=vote_options,
                horizontal=True,
                key=f"vote_{post['id']}"
            )
            
            if st.button("Submit Vote", key=f"submit_{post['id']}"):
                user_ip = st.query_params.get("ip", ["unknown"])[0]
                actual_model = get_actual_model_name(selected_vote)
                save_vote(thread['id'], post['id'], actual_model, user_ip)
                st.success("Vote submitted successfully!")
        
        # Translations
        for i, model in enumerate(models, 1):
            with post_columns[i]:
                display_name = get_model_display_name(model)
                st.markdown(f"**{display_name}**")
                st.markdown(f"**User:** {post['username']}")
                st.markdown("---")
                if model in post['message_english']:
                    st.markdown(post['message_english'][model]['text'])
                else:
                    st.markdown("*No translation available*")

                # Token usage
                if post['message_english'][model]['tokens']['prompt_tokens']:
                    st.markdown(f"**Prompt tokens:** {post['message_english'][model]['tokens']['prompt_tokens']}")
                if post['message_english'][model]['tokens']['completion_tokens']:
                    st.markdown(f"**Completion tokens:** {post['message_english'][model]['tokens']['completion_tokens']}")
                if post['message_english'][model]['tokens']['total_tokens']:
                    st.markdown(f"**Total tokens:** {post['message_english'][model]['tokens']['total_tokens']}")
        
        st.markdown("---")

if __name__ == "__main__":
    main() 