# app/services/analyzer.py
import os
import json
import re
import httpx
from dotenv import load_dotenv

class ProjectAnalyzer:
    """
    Kage: The silent blade. This module, ProjectAnalyzer, serves to distill
    the essence of a software project, revealing its core components,
    achievements, and underlying complexity. It operates with precision,
    extracting truth from raw data.
    """
    MAX_CONTENT_LENGTH = 15000  # Max content length for prompt

    def __init__(self, model_name: str = "gemini-2.0-flash", api_key: str = None):
        """
        Kage: Initializing the ProjectAnalyzer. A weapon requires a wielder.
        Without the GEMINI_API, this blade remains sheathed.
        """
        if not api_key:
            raise ValueError("GEMINI_API environment variable not set. API key is required for ProjectAnalyzer. The path is unclear without it.")
        self.api_key = api_key
        self.model_name = model_name
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        print(f"[Kage] ProjectAnalyzer initialized. Gemini model: {self.model_name}. A tool sharpened for insight.")

    def _sanitize_text(self, text: str) -> str:
        """
        Kage: Cleansing the input. Noise obscures truth. This function
        removes impurities, ensuring only clear data remains for analysis.
        """
        if not isinstance(text, str):
            return ""
        text = text.encode('ascii', 'ignore').decode('ascii')
        replacements = {
            '“': '"', '”': '"', '‘': "'", '’': "'", '—': '--', '–': '-', '…': '...',
            '\u2013': '-', '\u2014': '--', '\u2019': "'", '\u201c': '"', '\u201d': '"',
            '\u2022': '*', '\u00a0': ' '
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return re.sub(r'[\x00-\x1F\x7F]+', '', text).strip()

    def _generate_prompt_messages(self, data: dict) -> list:
        """
        Kage: Crafting the query. The prompt is the focal point, directing
        the external intelligence to reveal the project's true form.
        """
        def limit_and_sanitize(content):
            """Internal function for concise data preparation."""
            text = self._sanitize_text(content)
            if len(text) > self.MAX_CONTENT_LENGTH:
                return text[:self.MAX_CONTENT_LENGTH] + "\n... (truncated)"
            return text or "N/A"

        readme = limit_and_sanitize(data.get('readme_content', ''))
        commits = "\n".join([self._sanitize_text(c) for c in data.get('recent_commits', [])])
        commits = limit_and_sanitize(commits)

        jupyter_note = ""
        if data.get('has_jupyter_notebooks'):
            jupyter_note = "Should performance metrics be present within Jupyter notebooks, extract them."

        content = f"""
Analyze this software project. Output solely valid JSON with the following keys:
- skills (list of strings)
- technologies (list of strings)
- achievements (list of strings)
- summary (string)
- keywords (list of strings)
- estimated_complexity_qualitative (string)
- performance_metrics (object)

Project Name: {self._sanitize_text(data.get('name', 'Unnamed'))}
Description: {self._sanitize_text(data.get('description', 'No description.'))}
Languages: {self._sanitize_text(', '.join(data.get('languages', {}).keys()) or 'N/A')}
Dependencies: {self._sanitize_text(', '.join(data.get('dependencies', [])) or 'N/A')}

README:
{readme}

Commits:
{commits}

{jupyter_note}

Return JSON ONLY. No other prose.
"""
        return [{"role": "user", "parts": [{"text": content.strip()}]}]

    async def analyze_project(self, data: dict) -> dict:
        """
        Kage: Engaging the external mind. This is the act of perception,
        where the project's data is presented for its true nature to be
        revealed.
        """
        messages = self._generate_prompt_messages(data)
        name = data.get('name', 'Unknown')

        try:
            print(f"[Kage] Initiating analysis for '{name}'. Seeking clarity.")

            payload = {
                "contents": messages,
                "generationConfig": {
                    "temperature": 0.2, # Precision, not wild speculation.
                    "topK": 40,
                    "topP": 1.0,
                    "maxOutputTokens": 2048
                }
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.api_url,
                    headers={'Content-Type': 'application/json'},
                    json=payload,
                    timeout=300.0
                )
                response.raise_for_status()
                result = response.json()

                try:
                    json_str = result['candidates'][0]['content']['parts'][0]['text']
                except (KeyError, IndexError, TypeError):
                    print(f"[Kage] ❌ Observation corrupted for '{name}'. Unexpected response structure.")
                    return self._fallback(name, "Invalid external response structure.")

                # Remove external formatting if present. Only the core matters.
                json_str = json_str.strip()
                if json_str.startswith("```"):
                    json_str = "\n".join(json_str.split("\n")[1:])
                if json_str.endswith("```"):
                    json_str = "\n".join(json_str.split("\n")[:-1])

                try:
                    parsed = json.loads(json_str)
                    parsed.setdefault('performance_metrics', {}) # Ensure structure.
                    print(f"[Kage] Analysis complete for '{name}'. Clarity achieved.")
                    return parsed
                except json.JSONDecodeError as e:
                    print(f"[Kage] ❌ Flawed interpretation for '{name}'. JSON format compromised. Error: {e}. Partial data: {json_str[:500]}...")
                    return self._fallback(name, f"JSON parsing failed: {e}")

        except httpx.RequestError as e:
            print(f"[Kage] ❌ Connection severed during analysis of '{name}'. Network impediment: {e}")
            return self._fallback(name, f"Network error during external analysis: {e}")
        except httpx.HTTPStatusError as e:
            print(f"[Kage] ❌ External intelligence resisted for '{name}'. Status: {e.response.status_code}. Response: {e.response.text}")
            return self._fallback(name, f"External API error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            print(f"[Kage] ❌ An unknown shadow appeared during '{name}' analysis. Error: {e}")
            return self._fallback(name, f"Unexpected error during external analysis: {e}")

    def _fallback(self, name="Unknown", reason="Analysis failed.") -> dict:
        """
        Kage: When the path is obscured, a default response is formed.
        It is not a complete victory, but a controlled retreat.
        """
        return {
            "skills": [],
            "technologies": [],
            "achievements": [f"Insight could not be fully gained for project '{name}': {reason}"],
            "summary": f"Detailed understanding for {name} is currently absent.",
            "keywords": [],
            "estimated_complexity_qualitative": "N/A",
            "performance_metrics": {}
        }

# Example Usage (for Silragon Ryu's observation)
if __name__ == "__main__":
    load_dotenv()
    gemini_api_key = os.getenv("GEMINI_API")

    if not gemini_api_key:
        print("GEMINI_API environment variable not set. The tool remains untested.")
    else:
        analyzer = ProjectAnalyzer(api_key=gemini_api_key)

        dummy_project_data = {
            "name": "My Awesome Python Project",
            "description": "A web application for managing tasks, built with Python and Flask.",
            "languages": {"Python": 90, "HTML": 10},
            "dependencies": ["Flask", "SQLAlchemy", "Jinja2"],
            "readme_content": """
# My Awesome Python Project

This project is a simple task management web application.

## Features
- User authentication
- Task creation, editing, and deletion
- Due date reminders

## Installation
`pip install -r requirements.txt`

## Performance
Initial tests show task creation takes ~100ms.
""",
            "recent_commits": [
                "feat: Add user authentication module",
                "fix: Corrected task deletion bug",
                "docs: Update README with installation instructions",
                "refactor: Improve database query performance"
            ],
            "has_jupyter_notebooks": False
        }

        dummy_ml_project_data = {
            "name": "Image Classifier with TensorFlow",
            "description": "A convolutional neural network (CNN) for classifying images of cats and dogs.",
            "languages": {"Python": 95, "Jupyter Notebook": 5},
            "dependencies": ["tensorflow", "keras", "numpy", "matplotlib"],
            "readme_content": """
# Image Classifier with TensorFlow

This project implements a CNN for image classification.

## Results
- Achieved 92.5% accuracy on the test set.
- Precision: 0.90, Recall: 0.88
- F1-score: 0.89
""",
            "recent_commits": [
                "feat: Initial CNN architecture",
                "perf: Optimize training loop",
                "docs: Add performance metrics to README",
                "refactor: Clean up data preprocessing"
            ],
            "has_jupyter_notebooks": True
        }

        import asyncio

        async def run_analysis_examples():
            print("\n--- Observing 'My Awesome Python Project' ---")
            analysis_result = await analyzer.analyze_project(dummy_project_data)
            print(json.dumps(analysis_result, indent=2))

            print("\n--- Observing 'Image Classifier with TensorFlow' ---")
            ml_analysis_result = await analyzer.analyze_project(dummy_ml_project_data)
            print(json.dumps(ml_analysis_result, indent=2))

        asyncio.run(run_analysis_examples())