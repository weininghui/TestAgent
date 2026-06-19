"""Agents package — sub-agent definitions, model presets, LLM wrappers.

Quick-start
-----------
    from agents.agent_defs import AgentRegistry, AgentRole, AgentCapability

    registry = AgentRegistry()
    scanner = registry.get("scanner")
    print(scanner.model)

Public API
----------
``agent_defs``
    AgentRole, AgentCapability, AgentDefinition, AgentRegistry

``models``
    ModelConfig, get_llm(), get_model(), save_config(), load_config()

``config``
    PipelineConfig

``llm``
    LLMWrapper

``multi_agent``
    MultiAgentPipeline

``prompts``
    PromptBuilder, Technique, TechniqueSelector, per-stage builders
"""

from agents import agent_defs, config, llm, models, multi_agent, prompts

__all__ = [
    "agent_defs",
    "config",
    "llm",
    "models",
    "multi_agent",
    "prompts",
]

