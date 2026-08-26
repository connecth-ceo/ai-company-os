from collections.abc import Iterable

from app.agents.definitions import AgentDefinition


class AgentRegistryError(ValueError):
    pass


class DuplicateAgentError(AgentRegistryError):
    pass


class UnknownAgentError(AgentRegistryError):
    pass


class AgentRegistry:
    """In-memory Phase 1 registry for versioned AgentDefinitions."""

    def __init__(self, definitions: Iterable[AgentDefinition] = ()) -> None:
        self._definitions: dict[str, AgentDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: AgentDefinition) -> None:
        if definition.key in self._definitions:
            raise DuplicateAgentError(f"Agent '{definition.key}' is already registered")
        self._definitions[definition.key] = definition

    def get(self, key: str) -> AgentDefinition | None:
        return self._definitions.get(key)

    def require(self, key: str) -> AgentDefinition:
        definition = self.get(key)
        if definition is None:
            raise UnknownAgentError(f"Agent '{key}' is not registered")
        return definition

    def all(self) -> tuple[AgentDefinition, ...]:
        return tuple(self._definitions.values())

    def __contains__(self, key: str) -> bool:
        return key in self._definitions

    def __len__(self) -> int:
        return len(self._definitions)
