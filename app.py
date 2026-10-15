import os
import tempfile

import streamlit as st

from summarizer import STYLES, read_file, summarize_long

st.set_page_config(page_title="AI File Summarizer", page_icon="📄")

st.title("📄 AI File Summarizer")
st.write("Upload a text, Word, or PDF file and get a summary.")
st.caption("Don't upload confidential files. Requests to the free API are logged.")

style = st.selectbox("Summary style", list(STYLES))
uploaded = st.file_uploader("Choose a file", type=["txt", "md", "pdf", "docx"])


if uploaded is not None and st.button("Summarize"):
    st.session_state.pop("summary", None)   # remove any old result
    # Save the upload to a temporary file so read_file() can open it by path
    suffix = os.path.splitext(uploaded.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = tmp.name

    try:
        text = read_file(tmp_path)
    finally:
        os.remove(tmp_path)

    if not text.strip():
        st.error("No text found in the file. A scanned PDF is an image and has no selectable text.")
    else:
        st.info(f"Read {len(text):,} characters.")
        progress = st.empty()
        try:
            with st.spinner("Summarizing..."):
                summary = summarize_long(text, style, on_progress=progress.text)
            progress.empty()
            st.session_state.summary = summary
            st.session_state.filename = os.path.splitext(uploaded.name)[0] + "_summary.txt"
        except RuntimeError as e:
            progress.empty()
            st.error(str(e))

# Show the latest summary (kept in session_state so it survives re-runs)
if "summary" in st.session_state:
    st.subheader("Summary")
    st.markdown(st.session_state.summary)
    st.download_button(
        "Download summary",
        st.session_state.summary,
        file_name=st.session_state.filename,
        mime="text/plain",
    )