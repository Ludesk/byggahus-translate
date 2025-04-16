import streamlit as st
import json
from pathlib import Path
import string
from pymongo import MongoClient
from datetime import datetime
import os
from dotenv import load_dotenv
import random
import pandas as pd
import plotly.express as px

# Load environment variables
load_dotenv()

# Initialize session state for model mapping if not exists
if 'model_mapping' not in st.session_state:
    st.session_state.model_mapping = {}

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

def remove_vote(thread_id, post_id, user_ip):
    db = get_db()
    if db is not None:
        db.votes.delete_one({
            "thread_id": thread_id,
            "post_id": post_id,
            "user_ip": user_ip
        })

# Load the translated threads
@st.cache_data
def load_threads():
    with open('translated_threads.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def get_translation_models(thread):
    """Get all unique translation models used in the thread"""
    models = set()
    # Get models from title translations
    models.update(thread['title_english'].keys())
    # Get models from post translations
    for post in thread['posts']:
        models.update(post['message_english'].keys())
    return list(models)

def get_randomized_models(models, thread_id, post_id=None):
    """Get a randomized list of models for the current thread and post"""
    if 'randomized_models' not in st.session_state:
        st.session_state.randomized_models = {}
    
    # Create a unique key for thread or thread+post
    key = f"{thread_id}_{post_id}" if post_id is not None else thread_id
    
    if key not in st.session_state.randomized_models:
        st.session_state.randomized_models[key] = random.sample(models, len(models))
    
    return st.session_state.randomized_models[key]

def get_model_display_name(model, thread_id, post_id=None, show_actual=False):
    """Get the display name for a model based on its position in the randomized list"""
    # Get the position in the randomized list
    position = st.session_state.randomized_models[f"{thread_id}_{post_id}" if post_id is not None else thread_id].index(model) + 1
    display_name = f"Model {chr(64 + position)}"  # 65 is ASCII for 'A'
    
    if show_actual:
        return f"{display_name} ({model})"
    return display_name

def get_actual_model_name(display_name, thread_id, post_id=None):
    """Get the actual model name from the display name"""
    # Extract the position from the display name (e.g., "Model A" -> 1)
    position = ord(display_name.split()[-1]) - 64  # Convert 'A' to 1, 'B' to 2, etc.
    
    # Get the model at this position in the randomized list
    key = f"{thread_id}_{post_id}" if post_id is not None else thread_id
    if key in st.session_state.randomized_models:
        models = st.session_state.randomized_models[key]
        if 0 < position <= len(models):
            return models[position - 1]
    return display_name  # Fallback to the display name if no match found

def get_all_vote_stats():
    """Get vote statistics for all models across all threads and posts"""
    db = get_db()
    if db is not None:
        pipeline = [
            {"$group": {
                "_id": "$model",
                "count": {"$sum": 1}
            }}
        ]
        results = list(db.votes.aggregate(pipeline))
        return {result["_id"]: result["count"] for result in results}
    return {}

def get_user_vote(thread_id, post_id, user_ip):
    db = get_db()
    if db is not None:
        votes = list(db.votes.find({
            "thread_id": thread_id,
            "post_id": post_id,
            "user_ip": user_ip
        }))
        return [vote["model"] for vote in votes]
    return []

def show_statistics():
    st.title("Translation Model Statistics")
    st.markdown("---")
    
    # Get all vote statistics
    vote_stats = get_all_vote_stats()
    total_votes = sum(vote_stats.values())
    
    st.metric("Total Votes", total_votes)
    
    if total_votes > 0:
        # Create DataFrame for plotting
        df = pd.DataFrame({
            'Model': list(vote_stats.keys()),
            'Votes': list(vote_stats.values())
        })
        
        # Create bar chart
        fig = px.bar(df, 
                    x='Model', 
                    y='Votes',
                    title='Votes per Translation Model',
                    labels={'Model': 'Translation Model', 'Votes': 'Number of Votes'},
                    color='Model')
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Show detailed statistics
        st.subheader("Detailed Statistics")
        for model, votes in vote_stats.items():
            percentage = (votes / total_votes) * 100
            st.write(f"{model}: {votes} votes ({percentage:.1f}%)")
    else:
        st.info("No votes have been cast yet.")

def initialize_session_state():
    if 'voted_posts' not in st.session_state:
        st.session_state.voted_posts = set()
    if 'user_votes' not in st.session_state:
        st.session_state.user_votes = {}

def get_user_vote_from_session(thread_id, post_id, model):
    key = f"{thread_id}_{post_id}_{model}"
    return st.session_state.user_votes.get(key, False)

def save_user_vote_to_session(thread_id, post_id, model):
    key = f"{thread_id}_{post_id}_{model}"
    st.session_state.user_votes[key] = True

def remove_user_vote_from_session(thread_id, post_id, model):
    key = f"{thread_id}_{post_id}_{model}"
    if key in st.session_state.user_votes:
        del st.session_state.user_votes[key]

def main():
    st.set_page_config(
        page_title="Forum Thread Translations",
        page_icon="🌐",
        layout="wide"
    )
    
    # Initialize session state
    initialize_session_state()
    
    # Initialize MongoDB
    initialize_votes_collection()
    
    # Add page selection
    page = st.sidebar.selectbox(
        "Select a page:",
        ["Thread Translations", "Statistics"]
    )
    
    if page == "Thread Translations":
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
        
        # Get randomized models for thread title
        randomized_models = get_randomized_models(models, thread['id'])
        
        # Create columns for original and each translation model
        columns = st.columns(1 + len(models))
        
        # Display thread metadata
        with columns[0]:
            st.subheader("Original")
            st.markdown(f"**Title:** {thread['title']}")
        
        # Display title translations
        for i, model in enumerate(randomized_models, 1):
            with columns[i]:
                display_name = get_model_display_name(model, thread['id'])
                st.subheader(display_name)
                if model in thread['title_english']:
                    st.markdown(f"**Title :** {thread['title_english'][model]['text']}")
        
        st.markdown("---")
        
        # Display posts
        for post in thread['posts']:
            if post['position'] == 0:
                st.markdown(f"### Question")
            else:
                st.markdown(f"### Post {post['position']}")
            
            # Get randomized models for this post
            post_models = get_randomized_models(models, thread['id'], post['id'])
            
            # Create columns for this post
            post_columns = st.columns(1 + len(models))
            
            # Original post
            with post_columns[0]:
                st.markdown("**Original Post**")
                st.markdown(f"<span style='color: gray; font-size: 0.9em'>User: {post['username']}</span>", unsafe_allow_html=True)
                st.markdown(post['message'])
                
                # Show voting distribution under original column only if user has voted
                post_key = f"{thread['id']}_{post['id']}"
                if post_key in st.session_state.voted_posts:
                    vote_stats, total = get_vote_stats(thread['id'], post['id'])
                    if total > 0:
                        st.markdown("**Vote Distribution:**")
                        for model_name, count in vote_stats.items():
                            display_name = get_model_display_name(model_name, thread['id'], post['id'], show_actual=True)
                            percentage = (count / total) * 100
                            st.write(f"{display_name}: {count} votes ({percentage:.1f}%)")
            
            # Translations
            for i, model in enumerate(post_models, 1):
                with post_columns[i]:
                    display_name = get_model_display_name(model, thread['id'], post['id'])
                    st.markdown(f"**{display_name}**")
                    
                    st.markdown(f"<span style='color: gray; font-size: 0.9em'>User: {post['username']}</span>", unsafe_allow_html=True)
                    if model in post['message_english']:
                        st.markdown(post['message_english'][model]['text'])
                    else:
                        st.markdown("*No translation available*")
                    
                    # Add vote button for this translation
                    user_ip = st.query_params.get("ip", ["unknown"])[0]
                    has_voted = get_user_vote_from_session(thread['id'], post['id'], model)
                    
                    if has_voted:
                        if st.button("Remove Vote", key=f"remove_{post['id']}_{model}", type="primary", use_container_width=True):
                            remove_vote(thread['id'], post['id'], user_ip)
                            remove_user_vote_from_session(thread['id'], post['id'], model)
                            st.success("Vote removed successfully!")
                            st.rerun()
                    else:
                        if st.button("Vote for this translation", key=f"vote_{post['id']}_{model}", use_container_width=True):
                            save_vote(thread['id'], post['id'], model, user_ip)
                            save_user_vote_to_session(thread['id'], post['id'], model)
                            # Add this post to the voted_posts set
                            post_key = f"{thread['id']}_{post['id']}"
                            st.session_state.voted_posts.add(post_key)
                            st.success("Vote submitted successfully!")
                            st.rerun()
                    
                    # Show model name in gray if user has voted
                    post_key = f"{thread['id']}_{post['id']}"
                    if post_key in st.session_state.voted_posts:
                        st.markdown(f"<span style='color: gray; font-size: 0.9em'>Model: {model}</span>", unsafe_allow_html=True)

            st.markdown("---")
    else:
        show_statistics()

if __name__ == "__main__":
    main() 