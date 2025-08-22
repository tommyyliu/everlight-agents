def generate_dm_name(a_name: str, b_name: str) -> str:
    """Generate a stable DM name between two agents, ordered lexicographically."""
    names = sorted([a_name, b_name])
    return f"Direct Message between {names[0]} and {names[1]}"


def generate_self_dm_name(name: str) -> str:
    """Generate a stable self-DM name for an agent."""
    return f"Direct Message with {name} (self)"
