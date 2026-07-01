"""Data models for the resume agent."""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal


class ContactInfo(BaseModel):
    name: str
    email: str
    phone: str
    linkedin: str
    github: str = ""
    location: str
    scholar_url: str = ""


class Bullet(BaseModel):
    text: str
    tags: list[str] = []


class Experience(BaseModel):
    role: str
    org: str
    dates: str
    tags: list[str] = []
    bullets: list[Bullet] = []


class Project(BaseModel):
    name: str
    url: str = ""
    tags: list[str] = []
    bullets: list[Bullet] = []


class EducationEntry(BaseModel):
    degree: str
    institution: str
    dates: str = ""
    location: str = ""
    details: list[str] = []


class Achievement(BaseModel):
    text: str
    tags: list[str] = []


class MasterResume(BaseModel):
    contact: ContactInfo
    experiences: list[Experience] = []
    projects: list[Project] = []
    skills: dict[str, list[str]] = {}
    education: list[EducationEntry] = []
    achievements: list[Achievement] = []


Track = Literal["technical", "leadership", "domain"]

TRACK_CONFIG: dict[str, dict] = {
    "technical": {
        "label": "Technical / Individual Contributor",
        "description": "Best for: ML Engineer, Data Scientist, Research Scientist, Software Engineer",
        "priority_tags": [
            "ml", "python", "statistics", "modeling", "pipeline", "hpc",
            "algorithms", "deep-learning", "nlp", "cv", "sql", "data-engineering",
            "software-engineering", "api", "docker", "cloud", "r", "pytorch",
            "scikit-learn", "xgboost", "lightgbm", "shap", "explainability",
        ],
        "boost_tags": ["publications", "open-source", "production"],
        "depriority_tags": ["stakeholder-management", "executive-reporting"],
    },
    "leadership": {
        "label": "Leadership / People Manager",
        "description": "Best for: Principal DS, Team Lead, Manager, Director",
        "priority_tags": [
            "leadership", "mentoring", "stakeholder-management", "cross-functional",
            "program-management", "communication", "strategy", "hiring",
            "project-management", "roadmap", "executive-reporting",
        ],
        "boost_tags": ["team-size", "budget", "org-design"],
        "depriority_tags": ["low-level-implementation"],
    },
    "domain": {
        "label": "Domain Expert / Research Scientist",
        "description": "Best for: Pharma, Biotech, Academic-adjacent, Clinical Research",
        "priority_tags": [
            "bioinformatics", "genomics", "proteomics", "drug-discovery", "cheminformatics",
            "molecular-dynamics", "structural-biology", "publications", "research",
            "clinical-data", "ngs", "multi-omics", "biomarker", "qsar",
            "scientific-communication", "patent",
        ],
        "boost_tags": ["peer-reviewed", "patent", "collaboration"],
        "depriority_tags": ["business-metrics", "revenue"],
    },
}
