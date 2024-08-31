import streamlit as st
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.chains.question_answering import load_qa_chain
from langchain_community.chat_models import ChatOpenAI
import os

OPENAI_API_KEY = " "  # Replace with your OpenAI API key
DATA_FOLDER = "wscadata"  # Folder where the text files are saved

# Streamlit app setup
st.header("WSCA Chatbot")

# Process all text files from the specified directory
def load_and_process_files(data_folder):
    texts = []
    for filename in os.listdir(data_folder):
        if filename.endswith(".txt"):
            file_path = os.path.join(data_folder, filename)
            with open(file_path, 'r', encoding='utf-8') as file:
                texts.append(file.read())
    return texts

# Extract and process the text from files
texts = load_and_process_files(DATA_FOLDER)

# Break the combined text into chunks
text_splitter = RecursiveCharacterTextSplitter(
    separators="\n",
    chunk_size=1000,
    chunk_overlap=150,
    length_function=len
)
chunks = []
for text in texts:
    chunks.extend(text_splitter.split_text(text))

# Generate embeddings
embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)

# Create the FAISS vector store
vector_store = FAISS.from_texts(chunks, embeddings)

# Get user question
user_question = st.text_input("Type Your Question Here")

if user_question:
    match = vector_store.similarity_search(user_question)

    # Define the LLM
    llm = ChatOpenAI(
        openai_api_key=OPENAI_API_KEY,
        temperature=0,
        max_tokens=900,
        model_name="gpt-3.5-turbo"
    )

    # Chain for QA
    chain = load_qa_chain(llm, chain_type="stuff")
    response = chain.run(input_documents=match, question=user_question)
    st.write(response)
