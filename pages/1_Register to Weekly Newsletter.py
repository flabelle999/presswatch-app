import streamlit as st
from registration import registration_form

def main():
    st.title("📧 Register to PressWatch Updates")
    st.write("Stay up to date with the latest telecom news and insights from Zhone.")
    st.divider()

    registration_form()

if __name__ == "__main__":
    main()