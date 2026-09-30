"""
Setup script for agent-chaos-monkey pip installation.
"""

from setuptools import setup, find_packages

setup(
    name="agent-chaos-monkey",
    version="1.0.0",
    description="Chaos Engineering and QA Reliability Testing for AI Agents (CrewAI & LLM Tools)",
    long_description=open("README.md", "r", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Google DeepMind Antigravity Team",
    author_email="antigravity@example.com",
    url="https://github.com/example/agent-chaos-monkey",
    packages=find_packages(include=["chaos_engine", "chaos_engine.*", "agent_chaos_monkey", "agent_chaos_monkey.*"]),
    install_requires=[
        "requests>=2.28.0",
        "pydantic>=1.10.0",
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.20.0",
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Testing",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.8",
)
