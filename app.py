import streamlit as st
import json
from pathlib import Path
import string

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
    return sorted(list(models))

def get_model_display_name(model, model_mapping):
    """Get the display name for a model (e.g., 'Model A')"""
    if model not in model_mapping:
        # Assign next available letter
        next_letter = string.ascii_uppercase[len(model_mapping)]
        model_mapping[model] = f"Model {next_letter}"
    return model_mapping[model]

def main():
    st.set_page_config(
        page_title="Forum Thread Translations",
        page_icon="🌐",
        layout="wide"
    )
    
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
    
    # Create a mapping of actual model names to display names
    model_mapping = {}
    
    # Create columns for original and each translation model
    columns = st.columns(1 + len(models))
    
    # Display thread metadata
    with columns[0]:
        st.subheader("Original")
        st.markdown(f"**Title:** {thread['title']}")
    
    # Display title translations
    for i, model in enumerate(models, 1):
        with columns[i]:
            display_name = get_model_display_name(model, model_mapping)
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
        
        # Translations
        for i, model in enumerate(models, 1):
            with post_columns[i]:
                display_name = get_model_display_name(model, model_mapping)
                st.markdown(f"**{display_name}**")
                st.markdown(f"**User:** {post['username']}")
                st.markdown("---")
                if model in post['message_english']:
                    st.markdown(post['message_english'][model]['text'])
                else:
                    st.markdown("*No translation available*")
        
        st.markdown("---")

if __name__ == "__main__":
    main() 