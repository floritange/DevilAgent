# main.py
import os
import re
import yaml
import asyncio
import logging
from pathlib import Path
from typing import TypedDict, AsyncGenerator
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from ddgs import DDGS
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
logging.basicConfig(level=logging.WARNING, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
for name in ["httpx", "httpcore", "openai", "langchain", "urllib3"]:
    logging.getLogger(name).setLevel(logging.WARNING)


# ============ Search Validation Schema ============
class SearchValidation(BaseModel):
    """LLM validates if search results are satisfactory"""

    is_satisfied: bool = Field(description="True if results contain current/relevant date info")
    reason: str = Field(default="", description="Brief reason")
    new_queries: list[str] = Field(default=[], description="New queries if not satisfied, must include date")


# ============ Constants ============
SKILLS_DIR = Path(__file__).parent / "skills"
MAX_SKILL_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_DESCRIPTION_LENGTH = 1024


# ============ Search Intent Schema ============
class SearchQueries(BaseModel):
    """LLM output schema for extracting search keywords"""

    queries: list[str] = Field(default=[], description="1-3 concise search keywords extracted from user query.")


# ============ SkillMetadata TypedDict ============
class SkillMetadata(TypedDict):
    name: str
    description: str
    path: str
    content: str  # L2: full instruction for on-demand loading
    license: str | None
    compatibility: str | None
    metadata: dict
    allowed_tools: list[str]


# ============ Skill Functions ============
def _validate_skill_name(name: str, directory_name: str) -> tuple[bool, str]:
    """Validate skill name format"""
    if not name:
        return False, "Skill name cannot be empty"
    if len(name) > 64:
        return False, f"Skill name too long: {len(name)} > 64"
    # Only lowercase letters, numbers, single hyphens
    if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name):
        return False, f"Invalid skill name format: {name}"
    if name != directory_name:
        return False, f"Skill name '{name}' doesn't match directory '{directory_name}'"
    return True, ""


def _parse_skill_metadata(content: str, skill_path: str, directory_name: str) -> SkillMetadata | None:
    """Parse SKILL.md frontmatter"""
    if len(content) > MAX_SKILL_FILE_SIZE:
        logger.warning(f"Skipping {skill_path}: content too large ({len(content)} bytes)")
        return None

    # Extract YAML frontmatter between ---
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        logger.warning(f"Skipping {skill_path}: no valid YAML frontmatter")
        return None

    try:
        fm = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        logger.warning(f"Invalid YAML in {skill_path}: {e}")
        return None

    if not isinstance(fm, dict) or not fm.get("name") or not fm.get("description"):
        logger.warning(f"Skipping {skill_path}: missing name or description")
        return None

    # Validate name (warn but continue)
    is_valid, err = _validate_skill_name(fm["name"], directory_name)
    if not is_valid:
        logger.warning(f"Skill name warning for {skill_path}: {err}")

    desc = fm["description"]
    if len(desc) > MAX_DESCRIPTION_LENGTH:
        desc = desc[:MAX_DESCRIPTION_LENGTH] + "..."

    return SkillMetadata(
        name=fm["name"],
        description=desc,
        path=skill_path,
        content=content,
        license=fm.get("license"),
        compatibility=fm.get("compatibility"),
        metadata=fm.get("metadata", {}),
        allowed_tools=fm.get("allowed-tools", "").split() if fm.get("allowed-tools") else [],
    )


def _list_skills(source_path: Path) -> list[SkillMetadata]:
    """List all skills from directory"""
    skills = []
    if not source_path.exists():
        logger.warning(f"Skills directory not found: {source_path}")
        return skills

    for skill_dir in source_path.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            content = skill_md.read_text(encoding="utf-8")
            metadata = _parse_skill_metadata(content, str(skill_md), skill_dir.name)
            if metadata:
                skills.append(metadata)
        except Exception as e:
            logger.warning(f"Failed to parse {skill_md}: {e}")

    logger.info(f"Loaded {len(skills)} skills: {[s['name'] for s in skills]}")
    return skills


# ============ Search ============


async def _search_web(query: str) -> str:
    """Execute single search"""
    try:
        tool = DDGS()  # Fresh instance each search
        results = await asyncio.to_thread(tool.text, query, region="wt-wt", max_results=5)
        logger.debug(f"Search '{query}': got {len(results) if results else 0} results")
        if not results:
            return f"[No results: {query}]"
        return "\n".join(
            [f"- {r.get('title','')}: {r.get('body','')[:200]}...\n  Source: {r.get('href','')}" for r in results]
        )
    except Exception as e:
        logger.error(f"Search error '{query}': {e}")
        return f"[Search failed: {e}]"


async def multi_search(queries: list[str]) -> dict[str, str]:
    """Concurrent search for multiple queries"""
    logger.info(f"Multi-search: {queries}")
    results = await asyncio.gather(*[_search_web(q) for q in queries])
    return dict(zip(queries, results))


# ============ Prompts ============
NORMAL_PROMPT = """<system>
You are a helpful assistant. Follow instructions precisely. Do NOT invent facts.
</system>

<instructions>
1) Include source links when possible
2) Mark unverified info with "⚠️ Unverified"
3) Use search results if provided, verify dates match current date
</instructions>"""

DEVIL_PROMPT = """<system>
You are a professional red-team reviewer (Devil's Advocate mode). Find ALL issues and vulnerabilities strictly.
</system>

<instructions>
Task steps:
1) Analyze user content thoroughly
2) Identify logic flaws, technical issues, potential risks
3) Categorize findings by severity
4) Ask "Want deeper analysis on any specific issue?"
</instructions>

<context>
Available skills (L1 metadata):
{skills_list}

Active skill instructions (L2):
{skill_content}
</context>

<output_format>
🔴 **MUST FIX** - Critical/blocking issues
🟡 **SHOULD FIX** - Medium issues  
📝 **SUGGESTIONS** - Optimization tips

End with: "Want deeper analysis on any issue? You can specify attack direction."
</output_format>"""


# ============ DevilAgent ============
class DevilAgent:
    def __init__(self, model: str = "gpt-4o-mini", api_key: str = None, base_url: str = None):
        self.llm = ChatOpenAI(model=model, api_key=api_key, base_url=base_url, streaming=True)
        self.skills_metadata: list[SkillMetadata] = []
        self.devil_mode = True
        self.use_web_search = True  # User-controlled web search toggle
        self.active_skill: SkillMetadata | None = None
        self.history: list = []
        self._load_skills()
        logger.info(f"DevilAgent init | model={model} | skills={len(self.skills_metadata)}")

    def _load_skills(self):
        """Load L1 metadata at startup"""
        self.skills_metadata = _list_skills(SKILLS_DIR)

    def _format_skills_list(self) -> str:
        """Format L1 skills for prompt"""
        if not self.skills_metadata:
            return "No skills available"
        return "\n".join(
            [
                f"- **{s['name']}**: {s['description']}\n  → Read {s['path']} for full instructions"
                for s in self.skills_metadata
            ]
        )

    def _detect_skill(self, text: str) -> str:
        """Auto-detect content type"""
        if any(kw in text.lower() for kw in ["def ", "class ", "import ", "function", "```"]):
            return "code-checker"
        if any(
            kw in text.lower()
            for kw in [
                "paper",
                "report",
                "proposal",
                "design",
                "analysis",
                "hypothesis",
                "conclusion",
                "thesis",
                "research",
                "study",
            ]
        ):
            return "logic-auditor"
        return "general-reviewer"

    def _load_skill_by_name(self, name: str) -> SkillMetadata | None:
        """Load L2 content by name"""
        for s in self.skills_metadata:
            if s["name"] == name:
                logger.info(f"Loaded L2 skill: {name}")
                return s
        logger.warning(f"Skill not found: {name}")
        return None

    def set_mode(self, devil: bool):
        self.devil_mode = devil
        self.active_skill = None
        logger.info(f"Mode: {'Devil' if devil else 'Normal'}")

    def _build_prompt(self, user_input: str = "") -> str:
        if not self.devil_mode:
            return NORMAL_PROMPT
        # Auto-load skill in devil mode
        if user_input and not self.active_skill:
            skill_name = self._detect_skill(user_input)
            self.active_skill = self._load_skill_by_name(skill_name)
        skill_content = self.active_skill["content"] if self.active_skill else "No skill loaded"
        return DEVIL_PROMPT.format(skills_list=self._format_skills_list(), skill_content=skill_content)

    async def _extract_search_queries(self, user_input: str) -> list[str]:
        """Use LLM to extract search keywords from user query"""
        today = datetime.now().strftime("%Y-%m-%d")
        prompt = f"""Current date: {today}
Extract 1-3 search keywords. For time-sensitive queries (weather/news/stock/events), MUST include "{today}".
Examples:
"What's the weather in Beijing today" -> ["Beijing weather {today}"]
"Latest AI news" -> ["AI news {today}"]
"Check Tesla stock price" -> ["Tesla stock price {today}"]
"What is machine learning" -> ["machine learning tutorial"]"""

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_input},
        ]
        try:
            llm = ChatOpenAI(
                model=self.llm.model_name, api_key=self.llm.openai_api_key, base_url=self.llm.openai_api_base
            )
            structured = llm.with_structured_output(SearchQueries, method="json_schema", include_raw=True)
            logger.debug(f"[SearchQueries] Extracting from: {user_input[:50]}...")
            raw_result = await structured.ainvoke(messages)
            result = raw_result.get("parsed") if isinstance(raw_result, dict) else raw_result
            if result is None:
                logger.warning(f"[SearchQueries] Parsed is None")
                return []
            logger.info(f"Search queries: {result.queries}")
            return result.queries
        except Exception as e:
            logger.error(f"Search query extraction failed: {e}")
            return []

    async def _validate_search(self, user_input: str, results: dict[str, str]) -> SearchValidation | None:
        """ReACT: Check if search results satisfy the query (especially date relevance)"""
        today = datetime.now().strftime("%Y-%m-%d")
        results_text = "\n".join([f"[{q}]: {r[:300]}" for q, r in results.items()])
        prompt = f"""Current date: {today}
User asked: {user_input}
Search results:
{results_text}

Check: Do results contain info relevant to TODAY ({today})? If results show old dates, NOT satisfied."""
        try:
            llm = ChatOpenAI(
                model=self.llm.model_name, api_key=self.llm.openai_api_key, base_url=self.llm.openai_api_base
            )
            structured = llm.with_structured_output(SearchValidation, method="json_schema", include_raw=True)
            raw = await structured.ainvoke([{"role": "user", "content": prompt}])
            result = raw.get("parsed") if isinstance(raw, dict) else raw
            logger.info(
                f"Search validation: satisfied={result.is_satisfied}, reason={result.reason[:50] if result else 'None'}"
            )
            return result
        except Exception as e:
            logger.error(f"Search validation error: {e}")
            return None

    def set_search(self, enabled: bool):
        """Toggle web search on/off"""
        self.use_web_search = enabled
        logger.info(f"Web search: {'ON' if enabled else 'OFF'}")

    async def chat(self, user_input: str) -> AsyncGenerator[str, None]:
        """Stream chat with search support"""
        logger.info(
            f"Chat started | input: {user_input[:50]}... | search: {self.use_web_search} | devil: {self.devil_mode}"
        )
        self.history = []  # Independent session - fresh context each time
        search_context = ""
        search_sources = []
        if self.use_web_search:
            yield "[STAGE]Extracting search queries...\n"
            # ReACT search loop: Extract → Search → Validate → Retry if needed
            all_results = {}
            max_iterations = 3
            queries = await self._extract_search_queries(user_input)
            logger.debug(f"Extracted queries: {queries}")
            iteration_count = 0
            for i in range(max_iterations):
                if not queries:
                    logger.debug(f"No queries at iteration {i+1}, breaking")
                    break
                yield f"[STAGE]Searching: {', '.join(queries)}\n"
                logger.info(f"ReACT iteration {i+1}: searching {queries}")
                results = await multi_search(queries)
                all_results.update(results)
                iteration_count = i + 1
                logger.debug(f"Iteration {i+1} got {len(results)} results")
                yield f"[STAGE]Found {len(results)} results, validating...\n"
                # Validate search results
                validation = await self._validate_search(user_input, all_results)
                if validation is None or validation.is_satisfied:
                    logger.info(f"Search satisfied at iteration {i+1}")
                    break
                # Not satisfied, retry with new queries
                queries = validation.new_queries if validation.new_queries else []
                logger.info(f"Search not satisfied: {validation.reason}, new queries: {queries}")
                if queries:
                    yield f"[STAGE]Refining search...\n"
            else:
                logger.warning(f"Search max iterations reached")

            if all_results:
                today = datetime.now().strftime("%Y-%m-%d")
                # Extract sources for citation
                for q, r in all_results.items():
                    for line in r.split("\n"):
                        if "Source: " in line:
                            url = line.split("Source: ")[-1].strip()
                            if url and url.startswith("http"):
                                search_sources.append(url)
                search_context = (
                    f'\n\n<search_results date="{today}">\n'
                    + "\n".join([f"[{q}]\n{r}" for q, r in all_results.items()])
                    + f"\n</search_results>\n\nToday is {today}. Answer based on search results above. Use markdown formatting. Cite sources with [N](url) format when referencing specific facts."
                )
                logger.info(f"Search completed: {len(all_results)} results from {iteration_count} iteration(s)")
                logger.info(f"Extracted {len(search_sources)} source URLs")
                yield f"[STAGE]Generating response...\n"
        else:
            yield "[STAGE]Generating response (offline)...\n"
        self.history.append(HumanMessage(content=user_input))
        messages = [SystemMessage(content=self._build_prompt(user_input) + search_context)] + self.history
        full = ""
        try:
            async for chunk in self.llm.astream(messages):
                if chunk.content:
                    full += chunk.content
                    yield chunk.content
            # Add offline notice if no search
            if not self.use_web_search:
                yield "\n\n---\n⚠️ *Response generated without web search. Information may not be current.*"
            elif search_sources:
                yield "\n\n---\n**References:**\n"
                for i, src in enumerate(search_sources[:5], 1):
                    yield f"[{i}]: {src}\n"

            self.history.append(AIMessage(content=full))
            logger.info(f"Response: {len(full)} chars | history: {len(self.history)}")
        except Exception as e:
            logger.error(f"Chat error: {e}")
            yield f"\n[Error: {e}]"

    def clear(self):
        self.history = []
        self.active_skill = None
        logger.info("Cleared")


# ============ CLI ============
async def cli_main():
    agent = DevilAgent(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
    )
    print("DevilAgent | /devil toggle mode | /search toggle web | /clear reset | /quit exit\n")
    while True:
        try:
            inp = input("You: ").strip()
            if not inp:
                continue
            if inp == "/quit":
                break
            if inp == "/devil":
                agent.set_mode(not agent.devil_mode)
                print(f"-> {'Devil' if agent.devil_mode else 'Normal'}\n")
                continue
            if inp == "/search":
                agent.set_search(not agent.use_web_search)
                print(f"-> Web search: {'ON' if agent.use_web_search else 'OFF'}\n")
                continue
            if inp == "/clear":
                agent.clear()
                print("-> Cleared\n")
                continue
            print("AI: ", end="", flush=True)
            async for chunk in agent.chat(inp):
                print(chunk, end="", flush=True)
            print("\n")
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    asyncio.run(cli_main())
