# app/services/github_listener.py
import os
import json
import base64
import re
import xml.etree.ElementTree as ET
import toml
import yaml
from datetime import datetime
from dotenv import load_dotenv
from github import Github, Auth, UnknownObjectException


load_dotenv()

class GitHubListener:
    def __init__(self, github_token: str = None): # Modified: Accept token as argument
        """
        Initializes the GitHubListener.
        Args:
            github_token (str, optional): The GitHub personal access token to use.
            If None, it falls back to GITHUB_TOKEN environment variable.
        """
        self.github_token = github_token if github_token else os.getenv("GITHUB_TOKEN")
        if not self.github_token:
            raise ValueError(
                "GitHub token not provided and GITHUB_TOKEN environment variable not set. "
                "Please provide a token or set the environment variable."
            )

        self.auth = Auth.Token(self.github_token)
        self.g = Github(auth=self.auth)
        self._cached_repos = None
        # _authenticated_user_login is no longer cached here, as the listener is per-user instance
        # and the user object is fetched on demand for the current token.

        self.dependency_parsers = {
            "requirements.txt": self._parse_requirements_txt,
            "package.json": self._parse_package_json,
            "composer.json": self._parse_composer_json,
            "pubspec.yaml": self._parse_pubspec_yaml,
            "pom.xml": self._parse_pom_xml,
            "build.gradle": self._parse_build_gradle,
            "Gemfile": self._parse_gemfile,
            "go.mod": self._parse_go_mod,
            "Cargo.toml": self._parse_cargo_toml,
            "Podfile": self._parse_podfile,
        }

    def _get_authenticated_user(self):
        """
        Returns the authenticated GitHub user for the token associated with this instance.
        This method will now always fetch the user, as the instance is created per-user.
        """
        try:
            user = self.g.get_user()
            # print(f"Authenticated as: {user.login}") # Uncomment for debugging
            return user
        except Exception as e:
            print(f"Authentication failed with provided token: {e}")
            raise

    def get_all_user_repos(self, include_private=False, min_stars=0):
        """
        Fetches all repositories for the authenticated user, optionally including private ones.
        Caches the results for the current instance (which is per-user).
        """
        if self._cached_repos is not None:
            return self._cached_repos

        user = self._get_authenticated_user()
        repos = []
        print(f"Fetching repositories for {user.login}...")

        for repo in user.get_repos():
            # Skip the GitHub profile README repository (named after the user's login)
            if repo.name.lower() == user.login.lower():
                print(f"  Skipping profile README repository: {repo.name}")
                continue

            if not include_private and repo.private:
                continue
            if repo.fork:
                continue
            if not repo.private and repo.stargazers_count < min_stars:
                continue

            repos.append(repo)

        self._cached_repos = repos
        print(f"Finished fetching {len(repos)} repositories.")
        return repos

    def _get_file_content(self, repo, path):
        """Helper to get content of a file from a repo."""
        try:
            contents = repo.get_contents(path)
            return base64.b64decode(contents.content).decode('utf-8')
        except UnknownObjectException:
            return None
        except Exception as e:
            return None

    # --- Dependency Parsing Methods (Unchanged) ---
    def _parse_requirements_txt(self, content):
        dependencies = []
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('-'):
                dep_name = re.split(r'[=<>~]', line)[0].strip()
                dependencies.append(dep_name)
        return dependencies

    def _parse_package_json(self, content):
        dependencies = []
        try:
            data = json.loads(content)
            dependencies.extend(data.get('dependencies', {}).keys())
            dependencies.extend(data.get('devDependencies', {}).keys())
            dependencies.extend(data.get('peerDependencies', {}).keys())
        except json.JSONDecodeError:
            print("       Invalid package.json format.")
        return dependencies

    def _parse_composer_json(self, content):
        dependencies = []
        try:
            data = json.loads(content)
            dependencies.extend(data.get('require', {}).keys())
            dependencies.extend(data.get('require-dev', {}).keys())
        except json.JSONDecodeError:
            print("       Invalid composer.json format.")
        return dependencies

    def _parse_pubspec_yaml(self, content):
        dependencies = []
        try:
            data = yaml.safe_load(content)
            if 'dependencies' in data:
                dependencies.extend(data['dependencies'].keys())
            if 'dev_dependencies' in data:
                dependencies.extend(data['dev_dependencies'].keys())
        except yaml.YAMLError:
            print("       Invalid pubspec.yaml format.")
        return dependencies

    def _parse_pom_xml(self, content):
        dependencies = []
        try:
            root = ET.fromstring(content)
            ns = {'maven': 'http://maven.apache.org/POM/4.0.0'}
            for dep in root.findall('.//maven:dependency', ns):
                artifact_id_element = dep.find('maven:artifactId', ns)
                if artifact_id_element is not None:
                    dependencies.append(artifact_id_element.text)
        except ET.ParseError:
            print("       Invalid pom.xml format.")
        return dependencies

    def _parse_csproj(self, content):
        dependencies = []
        try:
            root = ET.fromstring(content)
            for package_ref in root.findall(".//PackageReference"):
                if 'Include' in package_ref.attrib:
                    dependencies.append(package_ref.attrib['Include'])
            for reference in root.findall(".//Reference"):
                if 'Include' in reference.attrib:
                    dependencies.append(reference.attrib['Include'].split(',')[0].strip())
            for import_stmt in root.findall(".//Import"):
                if 'Project' in import_stmt.attrib:
                    if '.targets' in import_stmt.attrib['Project'].lower():
                        pass
                    else:
                        dependencies.append(import_stmt.attrib['Project'].split('\\')[-1].replace('.props', '').replace('.targets', ''))
        except ET.ParseError:
            print("       Invalid .csproj format.")
        return dependencies

    def _parse_build_gradle(self, content):
        dependencies = []
        matches = re.findall(r'(?:implementation|api|compileOnly|runtimeOnly|testImplementation)\s*[\'"]([^\'"]+)[\'"]', content)
        for match in matches:
            parts = match.split(':')
            if len(parts) > 1:
                dependencies.append(parts[1])
            else:
                dependencies.append(parts[0])
        return dependencies

    def _parse_gemfile(self, content):
        dependencies = []
        matches = re.findall(r'gem\s*[\'"]([^\'"]+)[\'"]', content)
        dependencies.extend(matches)
        return dependencies

    def _parse_go_mod(self, content):
        dependencies = []
        matches = re.findall(r'^\s*require\s+([^\s]+)', content, re.MULTILINE)
        for match in matches:
            parts = match.split('/')
            dependencies.append(parts[0])
        return dependencies

    def _parse_cargo_toml(self, content):
        dependencies = []
        try:
            data = toml.loads(content)
            if 'dependencies' in data:
                dependencies.extend(data['dependencies'].keys())
            if 'dev-dependencies' in data:
                dependencies.extend(data['dev-dependencies'].keys())
            if 'build-dependencies' in data:
                dependencies.extend(data['build-dependencies'].keys())
        except Exception:
            print("       Invalid Cargo.toml format.")
        return dependencies

    def _parse_podfile(self, content):
        dependencies = []
        matches = re.findall(r"pod\s*['\"]([^'\"]+)['\"]", content)
        dependencies.extend(matches)
        return dependencies


    def _get_dependencies_from_repo(self, repo):
        """
        Attempts to find and parse common dependency files in a repository's root.
        Returns a list of identified dependencies.
        """
        dependencies = []

        for filename, parser in self.dependency_parsers.items():
            content = self._get_file_content(repo, filename)
            if content:
                try:
                    deps = parser(content)
                    dependencies.extend(deps)
                except Exception as e:
                    print(f"         Failed to parse {filename} for {repo.name}: {e}")

        try:
            root_contents = repo.get_contents("/")
            for item in root_contents:
                if item.type == "file":
                    if item.name.lower().endswith(".csproj"):
                        content = self._get_file_content(repo, item.name)
                        if content:
                            try:
                                deps = self._parse_csproj(content)
                                dependencies.extend(deps)
                            except Exception as e:
                                print(f"         Failed to parse {item.name} for {repo.name}: {e}")
                    elif item.name.lower().endswith((".java", ".kt")):
                        pass
        except UnknownObjectException:
            pass
        except Exception as e:
            print(f"         Error listing root contents for specific file checks in {repo.name}: {e}")

        return list(set(dependencies))

    def get_repo_details(self, repo):
        """
        Extracts detailed information from a single PyGithub Repository object.
        Args:
            repo (PyGithub.Repository.Repository): The repository object.
        Returns:
            dict: A dictionary of structured project data.
        """
        repo_data = {
            "id": repo.id,
            "name": repo.name,
            "full_name": repo.full_name,
            "description": repo.description if repo.description else "",
            "html_url": repo.html_url,
            "clone_url": repo.clone_url,
            "stargazers_count": repo.stargazers_count,
            "forks_count": repo.forks_count,
            "watchers_count": repo.subscribers_count,
            "created_at": repo.created_at.isoformat(),
            "updated_at": repo.updated_at.isoformat(),
            "last_pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
            "is_private": repo.private,
            "languages": {},
            "readme_content": "",
            "recent_commits": [],
            "dependencies": [],
            "has_jupyter_notebooks": False
        }

        try:
            repo_data["languages"] = repo.get_languages()
        except Exception as e:
            pass

        try:
            readme = repo.get_readme()
            repo_data["readme_content"] = base64.b64decode(readme.content).decode('utf-8')
        except UnknownObjectException:
            repo_data["readme_content"] = ""
        except Exception as e:
            repo_data["readme_content"] = ""

        try:
            commits = repo.get_commits(per_page=10)
            for i, commit in enumerate(commits):
                if i >= 10: break
                if commit.commit.message:
                    repo_data["recent_commits"].append(commit.commit.message.strip())
        except Exception as e:
            repo_data["recent_commits"] = []

        repo_data["dependencies"] = self._get_dependencies_from_repo(repo)

        try:
            contents = repo.get_contents("") 
            for content_file in contents:
                if content_file.type == "file" and content_file.name.lower().endswith(".ipynb"):
                    repo_data["has_jupyter_notebooks"] = True
                    print(f"  Detected Jupyter Notebook in {repo.name}")
                    break
        except UnknownObjectException:
            pass 
        except Exception as e:
            print(f"  Error checking for Jupyter notebooks in {repo.name}: {e}")

        return repo_data

    def get_all_project_data(self, include_private=False, min_stars=0):
        """
        Fetches detailed data for all relevant user repositories.
        Returns:
            list: A list of dictionaries, each representing a structured project.
        """
        all_repos = self.get_all_user_repos(include_private=include_private, min_stars=min_stars)
        project_data_list = []
        for repo in all_repos:
            try:
                details = self.get_repo_details(repo)
                project_data_list.append(details)
                print(f"  Successfully processed {repo.name}.")
            except Exception as e:
                print(f"Failed to get details for {repo.name}: {e}")

        print(f"\nSuccessfully gathered data for {len(project_data_list)} projects.")
        return project_data_list

# Example Usage:
if __name__ == "__main__":
    # Make sure you have 'toml' AND 'PyYAML' installed:
    # pip install toml PyYAML
    # For testing this directly, ensure GITHUB_TOKEN is set in your environment
    listener = GitHubListener() # Will use GITHUB_TOKEN env var
    try:
        print("Starting GitHub data fetching...")
        projects = listener.get_all_project_data(include_private=True, min_stars=0)

        if projects:
            print(f"\n--- Data for All {len(projects)} Projects ---")
            for project in projects:
                print(f"\nProject Name: {project['name']}")
                print(f"  Description: {project['description'][:100]}{'...' if len(project['description']) > 100 else ''}")
                print(f"  URL: {project['html_url']}")
                print(f"  Languages: {project['languages']}")
                if project['dependencies']:
                    print(f"  Dependencies ({len(project['dependencies'])}): {', '.join(project['dependencies'][:5])}{'...' if len(project['dependencies']) > 5 else ''}")
                else:
                    print("  Dependencies: None found")
                print(f"  Last Pushed: {project['last_pushed_at']}")
                print(f"  Is Private: {project['is_private']}")
                print(f"  Stars: {project['stargazers_count']}")
                if project['recent_commits']:
                    print(f"  Recent Commits ({len(project['recent_commits'])}):")
                    for commit_msg in project['recent_commits']:
                        print(f"    - {commit_msg[:70]}...")
                else:
                    print("  Recent Commits: N/A")
                print(f"  Has Jupyter Notebooks: {project.get('has_jupyter_notebooks', False)}")
            print("\n--- End of All Project Data ---")
        else:
            print("No projects found matching the criteria.")

    except ValueError as ve:
        print(f"Configuration Error: {ve}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
