import json
import logging
from pathlib import Path
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_skill_embeddings():
    skill_dir = Path("nexus/skills")
    if not skill_dir.exists():
        logger.warning(f"Skill directory {skill_dir} not found.")
        return

    logger.info("Loading semantic model to detect version...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    model_version = getattr(model, "__version__", "unknown")
    logger.info(f"Targeting model version: {model_version}")

    updated = 0
    for md_file in skill_dir.glob("**/*.md"):
        with open(md_file, "r") as f:
            content = f.read()
            
        if "embedding_model_version" in content:
            continue
            
        try:
            head, yaml_str, tail = content.split("---", 2)
            import yaml
            frontmatter = yaml.safe_load(yaml_str)
            if frontmatter and "skill_id" in frontmatter:
                frontmatter["embedding_model_version"] = model_version
                new_yaml = yaml.dump(frontmatter, sort_keys=False, allow_unicode=True)
                new_content = f"{head}---\n{new_yaml}---{tail}"
                with open(md_file, "w") as f:
                    f.write(new_content)
                updated += 1
                logger.debug(f"Migrated metadata for {md_file.name}")
        except Exception as e:
            logger.error(f"Failed to migrate {md_file.name}: {e}")

    logger.info(f"Migration complete: updated {updated} skills.")

if __name__ == "__main__":
    migrate_skill_embeddings()
