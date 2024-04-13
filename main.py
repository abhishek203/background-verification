# upload a resume
# find github link from the resume
# if there are multiple links find the root file
from math import ceil
import os
import fitz  # PyMuPDF
import re
from github import Github
import random
from openai import OpenAI
import streamlit as st

client = OpenAI(api_key=st.secrets["openai_api_key"])
github_api_key = st.secrets["github_api_key"]
def start_streamlit_app():
    st.title('Resume Upload for Code quality check')

    # Create a file uploader widget to accept PDF files
    uploaded_file = st.file_uploader("Choose a Resume/CV file", type="pdf")
    if uploaded_file is not None:
        # Display a message that the file is uploaded successfully
        st.success('File successfully uploaded.')

        # You can now pass this uploaded_file to any function that processes PDFs
        github_repo_links = list(extract_all_github_links(uploaded_file))
        random_links = random.sample(github_repo_links, min(len(github_repo_links), 4))
        progress_bar = st.progress(0.0)
        i = 0
        total_score = {"code smells":0,"code modularity":0,"code documentation/comments":0}
        for link in random_links:
            try:
                files = get_repo_files(link)
            except:
                continue
            inner_score = {"code smells":0,"code modularity":0,"code documentation/comments":0}
            count = 0
            for file in files:
                try:
                    scores = calculate_score(file)
                except:
                    continue
                for key, value in scores.items():
                    try:
                        inner_score[key] += int(value)
                    except:
                        pass
                count += 1
            if count == 0:
                continue
            for key,value in inner_score.items():
                inner_score[key] = round(inner_score[key]/count,2)
                total_score[key] += inner_score[key]
                
            progress_bar.progress(float((i+1)/len(random_links)))
            i+=1
        if i == 0:
            st.write("No repos found")
            return
        for key,value in total_score.items():
            total_score[key] = round(total_score[key]/i,2)
        progress_bar.progress(1.0)     
        col1, col2, col3 = st.columns(3)
        col1.metric("Code Smells",f"{total_score['code smells']}/10")
        col2.metric("Code Modularity", f"{total_score['code modularity']}/10")
        col3.metric("Code Documentation/Comments", f"{total_score['code documentation/comments']}/10")
        # Make sure to adjust the extract_all_github_links function to handle the uploaded file object

def process_files_in_data_folder():

    data_folder_path = './data'  # Assuming the data folder is in the same directory as this script
    for filename in os.listdir(data_folder_path):
        file_path = os.path.join(data_folder_path, filename)
        if os.path.isfile(file_path):
            print(f"Processing file: {filename}")
            # Add your file processing
            
            github_links = list(extract_all_github_links(file_path))
            print("Found GitHub links:", github_links)
            for github_link in github_links:
                repo_files = get_repo_files(github_link)
                print(f"Files in {github_link}:", repo_files)

def extract_all_github_links(uploaded_file):
    # Open the PDF file
    # doc = fitz.open(pdf_path)
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    
    # Regular expression to find GitHub links
    github_url_pattern = r'https://github\.com/[a-zA-Z0-9-]+/[a-zA-Z0-9-]+'
    github_url_pattern_base = r'https://github\.com/[a-zA-Z0-9_-]+$'
    # Container for found GitHub links
    github_links = set()
    
    # Iterate through each page of the PDF
    for page in doc:
        # Extract text from the current page and find GitHub links
        text = page.get_text()
        text_links = re.findall(github_url_pattern, text)
        for link in text_links:
            github_links.add(link)
        
        # Get all links from the current page and filter for GitHub links
        links = page.get_links()
        for link in links:
            if 'uri' in link and re.match(github_url_pattern, link['uri']):
                print('project link',link)
                github_links.add(link['uri'])
            if 'uri' in link and re.match(github_url_pattern_base,link['uri']):
                print('base link',link)
                github_links.update(list_repos_for_account(link['uri']))

    
    # Close the PDF document
    doc.close()
    
    # Return the set of GitHub links
    return github_links

def get_repo_files(github_url):
    # Extract the repository name from the URL
    path_parts = github_url.rstrip('/').split('/')
    repo_name = '/'.join(path_parts[-2:])  # user/repo

    g = Github(github_api_key)  # Initialize Github instance
    repo = g.get_repo(repo_name)  # Get the repository object

    contents = repo.get_contents("")  # List all contents of the repository root directory

    # Filter for files with specific extensions and get their content
    filtered_files_content = []
    while contents:
        file_content = contents.pop(0)
        if file_content.type == "dir":
            contents.extend(repo.get_contents(file_content.path))
        else:
            if file_content.path.endswith(('.py', '.js', '.cpp')):
                # Get the file content instead of the path
                file_data = file_content.decoded_content.decode('utf-8')
                filtered_files_content.append(file_data)

    # Return a random sample of max 9 files from the filtered list
    return random.sample(filtered_files_content, min(len(filtered_files_content), 3))

def generate_response_with_openai(system_prompt,content):
    
    response = client.chat.completions.create(
      model="gpt-4-turbo-preview",  
      messages=[{"role": "system", "content": system_prompt},
                {"role": "user", "content": content}],
      temperature=0.1,
      max_tokens=1,
      top_p=1.0,
      frequency_penalty=0.0,
      presence_penalty=0.0
    )
    
    return response.choices[0].message.content.strip()

def calculate_score(content):
    test_types = ['code smells','code modularity','code documentation/comments']
    len_content = len(content)
    print(len_content)
    if len_content > 4*1000:
        lines_to_get = ceil(len(content.splitlines())*(4*1000)/len_content)
        new_content = '\n'.join(content.splitlines()[-lines_to_get:])
    else:
        new_content = content
    print(new_content)
    res_dict = {}
    for test in test_types:
        system_prompt = f"On a scale of 1 to 10 what is the {test} status of the code snippet given by user. Answer should be an interger from 1 to 10."
        res_dict[test] = generate_response_with_openai(system_prompt,new_content)
    return res_dict

def list_repos_for_account(base_url):
    # Extract the account name from the URL
    account_name = base_url.rstrip('/').split('/')[-1]

    # Initialize Github instance (without authentication for public repos)
    g = Github(github_api_key)

    # Get the user by name
    user = g.get_user(account_name)

    # Fetch and print repository names
    repos = user.get_repos()
    repo_names = ['https://github.com/' + repo.full_name for repo in repos]
    return repo_names

if __name__ == "__main__":
    start_streamlit_app()
    # github_url = 'https://github.com/abhishek203'
    # a = (list_repos_for_account(github_url))
    # for x in a:
    #     print(get_repo_files(x))
    # print(list_repos_for_account(github_url))
    # process_files_in_data_folder()
    # x = (get_repo_files(github_url))
    # path_parts = github_url.rstrip('/').split('/')
    # repo_name = '/'.join(path_parts[-2:])  # user/repo

    # g = Github()  # Initialize Github instance
    # repo = g.get_repo(repo_name) 
    # print(len(x))
    # for a in x:
    #     print(repo.get_contents(a))
    
    # Example usage of the new function
    # print(calculate_score(x))
