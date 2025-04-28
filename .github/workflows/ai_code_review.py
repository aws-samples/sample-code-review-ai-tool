import json
import os
import boto3
from github import Github

def get_github_event():
    with open(os.environ['GITHUB_EVENT_PATH'], 'r') as f:
        return json.load(f)

def get_changed_files(repo, pr_number):
    pr = repo.get_pull(pr_number)
    return [file.filename for file in pr.get_files() if file.filename.endswith(('.py', '.tf', '.tfvars', '.hcl', '.yaml', '.yml'))]

def read_prompt_from_file():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_file_path = os.path.join(script_dir, 'prompt.txt')
    
    try:
        with open(prompt_file_path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"Error: prompt.txt not found in {script_dir}")
        return None

def analyze_code(file_content, file_name):
    bedrock = boto3.client('bedrock-runtime')

    # Add line numbers to the code
    numbered_content = "\n".join(f"{i+1}: {line}" for i, line in enumerate(file_content.split('\n')))

    prompt = read_prompt_from_file()
    if not prompt:
        return "Error: Unable to read prompt from file."

    message_content = f'''{prompt}

    File name: {file_name}
    Code (with line numbers):
    {numbered_content}'''

    body = json.dumps({
        'anthropic_version': 'bedrock-2023-05-31',
        'max_tokens': 2000,
        'messages': [
            {
                'role': 'user',
                'content': message_content
            }
        ],
        'temperature': 0.1,
        'top_p': 1
    })

    try:
        response = bedrock.invoke_model(
            modelId='anthropic.claude-3-sonnet-20240229-v1:0',
            body=body
        )

        response_body = json.loads(response['body'].read())
        completion = response_body['content'][0]['text']
        return completion
    except Exception as e:
        print(f'Error invoking Bedrock model: {str(e)}')
        return f'Error during code analysis: {str(e)}'

def main():
    github_token = os.environ.get('GITHUB_TOKEN')
    if not github_token:
        raise ValueError('GITHUB_TOKEN environment variable is not set')

    event = get_github_event()
    pr_number = event['pull_request']['number']
    repo_full_name = event['repository']['full_name']

    g = Github(github_token)
    repo = g.get_repo(repo_full_name)

    changed_files = get_changed_files(repo, pr_number)

    for file in changed_files:
        print(f'Debug: Analyzing file: {file}')
        content = repo.get_contents(file, ref=repo.get_pull(pr_number).head.sha).decoded_content.decode('utf-8', errors='ignore')
        # Ensure we preserve line breaks
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        ai_analysis = analyze_code(content, file)

        comment = f'''AI Code Review for `{file}`:

{ai_analysis}

Please review these findings and address any issues before merging.'''

        print(f'Debug: Posting comment for file: {file}')
        repo.get_issue(pr_number).create_comment(comment)

    print('AI Code Review completed successfully')

if __name__ == '__main__':
    main()
