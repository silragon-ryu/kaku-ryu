# app/services/scoring.py

from datetime import datetime, timedelta, timezone # Corrected import: added timezone directly

class ScoringEngine:
    def __init__(self):
        """
        Initializes the ScoringEngine.
        Future enhancements might include loading scoring weights from configuration.
        """
        print("[Kage Scoring] Scoring Engine initialized.")

    def calculate_score(self, project_data: dict) -> float:
        """
        Calculates a numerical score for a single project based on its analyzed data.
        
        The score can be based on various factors:
        - Estimated complexity (from LLM analysis)
        - Number/diversity of skills identified
        - Number/diversity of technologies used
        - Impact/quantifiable achievements (from LLM analysis)
        - Recency of last push/commits
        - Number of stars/forks (GitHub metrics)
        - Relevance of keywords to desired roles (future feature)
        - NEW: Presence and value of performance metrics (for ML/Data Science projects)

        Args:
            project_data (dict): A dictionary containing combined raw GitHub data
                                 and LLM-analyzed data (skills, achievements, summary, etc.).
                                 Expected keys include: 'estimated_complexity_qualitative',
                                 'skills', 'technologies', 'achievements', 'last_pushed_at',
                                 'stargazers_count', 'forks_count', 'languages',
                                 'has_jupyter_notebooks', 'performance_metrics'.
        Returns:
            float: The calculated score for the project.
        """
        score = 0.0

        # --- Base Score from Complexity ---
        complexity_map = {
            "Low": 10,
            "Medium": 30,
            "High": 60,
            "Very High": 100
        }
        complexity = project_data.get('estimated_complexity_qualitative', 'N/A')
        score += complexity_map.get(complexity, 0) # Add points based on complexity

        # --- Skills and Technologies (Increased Emphasis) ---
        # More skills/technologies generally mean a higher score
        skills_count = len(project_data.get('skills', []))
        tech_count = len(project_data.get('technologies', []))
        score += (skills_count * 8) # 8 points per skill
        score += (tech_count * 5)  # 5 points per technology

        # --- Achievements ---
        # Quantifiable achievements are highly valuable
        achievements_count = len(project_data.get('achievements', []))
        score += (achievements_count * 10) # 10 points per achievement

        # --- Recency ---
        # More recent projects are often more relevant
        last_pushed_at_str = project_data.get('last_pushed_at')
        if last_pushed_at_str:
            try:
                # Use datetime.fromisoformat directly on the imported datetime class
                last_pushed_at = datetime.fromisoformat(last_pushed_at_str.replace('Z', '+00:00'))
                
                # Use timezone.utc directly from the import
                now_utc = datetime.now(timezone.utc) 
                days_since_last_push = (now_utc - last_pushed_at).days

                # Award points for recency, e.g., higher for newer projects, decaying over time
                if days_since_last_push <= 30:
                    score += 20
                elif days_since_last_push <= 90:
                    score += 15
                elif days_since_last_push <= 180:
                    score += 10
                elif days_since_last_push <= 365:
                    score += 5
            except ValueError:
                print(f"[Kage Scoring] Warning: Invalid date format for last_pushed_at: {last_pushed_at_str}")
                pass # Continue without adding recency score

        # --- GitHub Metrics ---
        # Stars and forks can indicate community interest, but might not be relevant for private projects
        stars = project_data.get('stargazers_count', 0)
        forks = project_data.get('forks_count', 0)
        score += (stars * 0.5) # Half a point per star
        score += (forks * 1.0) # One point per fork

        # --- Language Diversity/Specifics (Expanded and Increased Emphasis) ---
        languages = project_data.get('languages', {})
        technologies_list = project_data.get('technologies', []) # Get as list for easier checking

        # Bonus points for key languages
        if 'Python' in languages:
            score += 20
        if 'JavaScript' in languages:
            score += 15
        if 'TypeScript' in languages:
            score += 15
        if 'Java' in languages:
            score += 15
        if 'C#' in languages:
            score += 15
        if 'Go' in languages:
            score += 10
        if 'Rust' in languages:
            score += 10
        if 'C++' in languages:
            score += 20
        if 'C' in languages:
            score += 15
        if 'PHP' in languages:
            score += 10
        if 'Ruby' in languages:
            score += 10
        if 'Swift' in languages:
            score += 15
        if 'Kotlin' in languages:
            score += 15
        if 'Scala' in languages:
            score += 10
        if 'R' in languages:
            score += 10


        # Bonus points for key frameworks/technologies (from LLM's 'technologies' list)
        if 'React' in technologies_list:
            score += 15
        if 'Angular' in technologies_list:
            score += 15
        if 'Vue.js' in technologies_list:
            score += 15
        if 'Django' in technologies_list:
            score += 10
        if 'Flask' in technologies_list:
            score += 10
        if 'Node.js' in technologies_list:
            score += 10
        if 'Docker' in technologies_list:
            score += 10
        if 'Kubernetes' in technologies_list:
            score += 15
        if 'AWS' in technologies_list or 'Azure' in technologies_list or 'GCP' in technologies_list: # Cloud
            score += 20
        if 'Jupyter Notebook' in technologies_list or 'Jupyter' in technologies_list:
            score += 10
        if 'TensorFlow' in technologies_list or 'PyTorch' in technologies_list: # ML Frameworks
            score += 15
        if 'SQL' in technologies_list or 'PostgreSQL' in technologies_list or 'MySQL' in technologies_list or 'MongoDB' in technologies_list: # Databases
            score += 10


        # Consider adding a small bonus for sheer diversity of languages (e.g., if > 2 languages)
        if len(languages) > 2:
            score += 5
        if len(languages) > 4:
            score += 10

        # NEW: Scoring based on Performance Metrics
        performance_metrics = project_data.get('performance_metrics', {})
        if performance_metrics:
            print(f"[Kage Scoring] Detected performance metrics for {project_data.get('name', 'Unnamed')}: {performance_metrics}")
            score += 25 # Base bonus for having any performance metrics

            # Example: Bonus for high accuracy (adjust threshold as needed)
            accuracy = performance_metrics.get('accuracy')
            if isinstance(accuracy, (int, float)) and accuracy >= 0.8:
                score += 30 # Significant bonus for high accuracy
            elif isinstance(accuracy, (int, float)) and accuracy >= 0.7:
                score += 15 # Moderate bonus

            # You can add similar logic for other metrics like f1_score, precision, etc.
            # For example:
            f1_score = performance_metrics.get('f1_score')
            if isinstance(f1_score, (int, float)) and f1_score >= 0.7:
                score += 10 # Bonus for good F1-score

        # Ensure score is not negative
        return max(0.0, score)

# Example Usage:
if __name__ == "__main__":
    # Dummy analyzed project data (this would come from analyzer.py's output)
    sample_analyzed_project = {
        "name": "Kaku-Ryu Dashboard",
        "description": "A personal dynamic resume engine that tracks GitHub projects.",
        "readme_content": "...", # Not directly used by scoring, but part of combined data
        "languages": {"Python": 10000, "HTML": 500, "CSS": 300, "JavaScript": 800, "TypeScript": 100, "C++": 2000}, # Added C++ for testing
        "dependencies": ["Flask", "Jinja2", "requests", "python-docx", "GitPython"],
        "recent_commits": ["...", "..."], # Not directly used by scoring

        # LLM Analyzed Data:
        "skills": ["Python", "FastAPI", "Jinja2", "Web Development", "API Integration", "Resume Generation", "Cloud Deployment", "Machine Learning"], # Added skill
        "technologies": ["Ollama", "Llama 3", "GitHub API", "HTML", "CSS", "JavaScript", "React", "Docker", "AWS", "Jupyter Notebook", "TensorFlow", "PostgreSQL"], # Added technologies
        "achievements": [
            "Developed AI-powered project analysis for resume generation.",
            "Integrated GitHub API for automated project tracking.",
            "Implemented dynamic resume generation in DOCX format.",
            "Deployed application using Docker on AWS."
        ],
        "summary": "A dynamic resume engine leveraging AI to automate resume updates from GitHub activity.",
        "keywords": ["AI", "Resume", "Automation", "GitHub", "LLM"],
        "estimated_complexity_qualitative": "High",
        "performance_metrics": {}, # No performance metrics for this
        "last_pushed_at": (datetime.now() - timedelta(days=20)).isoformat(), # Pushed 20 days ago
        "stargazers_count": 50,
        "forks_count": 5
    }

    scoring_engine = ScoringEngine()
    score = scoring_engine.calculate_score(sample_analyzed_project)
    print(f"\n[Kage Scoring] Score for '{sample_analyzed_project['name']}': {score:.2f}")

    # Another example with different characteristics
    simple_analyzed_project = {
        "name": "Simple Calculator App",
        "description": "A basic command-line calculator written in Python.",
        "readme_content": "...",
        "languages": {"Python": 200, "R": 50}, # Added R
        "dependencies": [],
        "recent_commits": ["initial commit", "add division feature"],

        # LLM Analyzed Data:
        "skills": ["Python", "Basic Arithmetic", "Data Analysis"], # Added skill
        "technologies": ["Jupyter"], # Added Jupyter
        "achievements": ["Developed a command-line calculator."],
        "summary": "A simple Python command-line calculator.",
        "keywords": ["Calculator", "Python", "CLI"],
        "estimated_complexity_qualitative": "Low",
        "performance_metrics": {}, # No performance metrics for this
        "last_pushed_at": (datetime.now() - timedelta(days=400)).isoformat(), # Pushed over a year ago
        "stargazers_count": 2,
        "forks_count": 0
    }

    score_simple = scoring_engine.calculate_score(simple_analyzed_project)
    print(f"[Kage Scoring] Score for '{simple_analyzed_project['name']}': {score_simple:.2f}")

    # Example with performance metrics
    ml_project_with_metrics = {
        "name": "Image Classifier with CNN",
        "description": "A deep learning project to classify images using Convolutional Neural Networks.",
        "readme_content": "...",
        "languages": {"Python": 15000, "Jupyter Notebook": 2000},
        "dependencies": ["tensorflow", "keras", "numpy", "matplotlib"],
        "recent_commits": ["initial model", "added data augmentation", "achieved 92% accuracy"],
        "has_jupyter_notebooks": True,
        # LLM Analyzed Data (simulated):
        "skills": ["Deep Learning", "CNNs", "Python", "Data Augmentation"],
        "technologies": ["TensorFlow", "Keras", "Jupyter Notebook"],
        "achievements": ["Developed image classification model", "Achieved 92% accuracy on test set"],
        "summary": "Image classification using CNNs, achieving high accuracy.",
        "keywords": ["AI", "Machine Learning", "Computer Vision"],
        "estimated_complexity_qualitative": "Very High",
        "performance_metrics": {"accuracy": 0.92, "f1_score": 0.88}, # Simulated extracted metrics
        "last_pushed_at": (datetime.now() - timedelta(days=10)).isoformat(),
        "stargazers_count": 100,
        "forks_count": 10
    }

    score_ml = scoring_engine.calculate_score(ml_project_with_metrics)
    print(f"\n[Kage Scoring] Score for '{ml_project_with_metrics['name']}': {score_ml:.2f}")
