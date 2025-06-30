from sqlalchemy.sql import roles
import streamlit as st
import openai 
from core.config import config 

client = openai.OpenAI(api_key=config.OPENAI_API_KEY) 

if "messages" not in st.session_state: 
    st.session_state.messages = [{"role": "assistant", "content": "Hello! How can I help you today?"}]

for message in st.session_state.messages: 
    with st.chat_message(message["role"]): 
        st.markdown(message["content"])
    
if prompt := st.chat_input("Hello! How can I help you today?"): 
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): 
        st.markdown(prompt)
    
    with st.chat_message("assistant"): 
        output = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[{"role": "user", "content": m["content"]} for m in st.session_state.messages],
            max_tokens=500
        )
        st.write(output.choices[0].message.content)
    st.session_state.messages.append({"role": "assistant", "content": output.choices[0].message.content})
    