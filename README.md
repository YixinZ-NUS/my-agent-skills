# insight-io Agent Skills

Agent Skills ([agentskills.io](https://agentskills.io) format) for the
[insight-io](https://github.com/YixinZ-NUS/insight-io) project.

These skills give GitHub Copilot CLI / Claude Code reusable procedural
knowledge and project-specific context that can be loaded on demand.

## Skills

| Skill | Description |
|-------|-------------|
| [`micro-experiment-documentation`](micro-experiment-documentation/SKILL.md) | Plan, execute, and document exploratory micro-experiments (codec paths, pipeline alternatives, hardware quirks, protocol variations). Includes rubber-duck checklist and guidance on overturning prior conclusions. |
| [`local-transcribe`](local-transcribe/SKILL.md) | Transcribe local audio or video files without an API key using ffmpeg extraction plus faster-whisper on CPU, with glossary prompting and automatic cleanup of temporary chunk WAVs. |

## Installation

Skills are installed in `~/.copilot/`:

```bash
# Clone into ~/.copilot
git clone https://github.com/YixinZ-NUS/insight-io-agent-skills.git /tmp/insight-io-agent-skills-src
cp -r /tmp/insight-io-agent-skills-src/micro-experiment-documentation ~/.copilot/
cp -r /tmp/insight-io-agent-skills-src/local-transcribe ~/.copilot/
```

Or to stay up to date, clone directly:

```bash
git clone https://github.com/YixinZ-NUS/insight-io-agent-skills.git ~/.copilot/insight-io-agent-skills
# Then symlink individual skills:
ln -s ~/.copilot/insight-io-agent-skills/micro-experiment-documentation \
      ~/.copilot/micro-experiment-documentation
ln -s ~/.copilot/insight-io-agent-skills/local-transcribe \
      ~/.copilot/local-transcribe
```

## License

MIT
