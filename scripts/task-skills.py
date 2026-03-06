#!/usr/bin/env python3
"""
task-skills - 列出和管理本地 Skills
"""

import argparse
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.skill_executor import list_available_skills, SkillManager


def main():
    parser = argparse.ArgumentParser(
        description="List and manage local OpenClaw Skills",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command")
    
    # 列出 skills
    list_parser = subparsers.add_parser("list", help="List available skills")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")
    list_parser.add_argument("--ready-only", action="store_true", help="Only show ready skills")
    
    # 查看 skill 详情
    info_parser = subparsers.add_parser("info", help="Show skill details")
    info_parser.add_argument("name", help="Skill name")
    
    # 检查 skill 依赖
    check_parser = subparsers.add_parser("check", help="Check skill requirements")
    check_parser.add_argument("name", help="Skill name")
    
    args = parser.parse_args()
    
    manager = SkillManager()
    
    if args.command == "list" or args.command is None:
        skills = list_available_skills()
        
        if hasattr(args, 'ready_only') and args.ready_only:
            skills = [s for s in skills if s['ready']]
        
        if hasattr(args, 'json') and args.json:
            print(json.dumps(skills, indent=2))
        else:
            print(f"\n{'Skill Name':<30} {'Ready':<8} {'Description'}")
            print("-" * 80)
            for skill in skills:
                status = "✓" if skill['ready'] else "✗"
                desc = skill['description'][:40] + "..." if len(skill['description']) > 40 else skill['description']
                print(f"{skill['name']:<30} {status:<8} {desc}")
            
            print(f"\nTotal: {len(skills)} skills")
            ready_count = sum(1 for s in skills if s['ready'])
            print(f"Ready: {ready_count}, Not ready: {len(skills) - ready_count}")
    
    elif args.command == "info":
        skill = manager.get_skill(args.name)
        if not skill:
            print(f"Skill not found: {args.name}")
            sys.exit(1)
        
        ok, missing = manager.check_requirements(skill)
        
        print(f"\n=== {skill.name} ===")
        print(f"Description: {skill.description}")
        print(f"Path: {skill.path}")
        print(f"Ready: {'Yes' if ok else 'No'}")
        
        if skill.requires_bins:
            print(f"\nRequired binaries: {', '.join(skill.requires_bins)}")
        
        if skill.requires_env:
            print(f"Required env vars: {', '.join(skill.requires_env)}")
        
        if missing:
            print(f"\nMissing requirements: {', '.join(missing)}")
        
        if skill.scripts:
            print(f"\nAvailable scripts:")
            for name, path in skill.scripts.items():
                print(f"  - {name}")
        
        if skill.commands:
            print(f"\nExample commands:")
            for cmd in skill.commands[:3]:
                print(f"  $ {cmd}")
    
    elif args.command == "check":
        skill = manager.get_skill(args.name)
        if not skill:
            print(f"Skill not found: {args.name}")
            sys.exit(1)
        
        ok, missing = manager.check_requirements(skill)
        
        if ok:
            print(f"✓ Skill '{args.name}' is ready to use")
            sys.exit(0)
        else:
            print(f"✗ Skill '{args.name}' has missing requirements:")
            for item in missing:
                print(f"  - {item}")
            sys.exit(1)


if __name__ == "__main__":
    main()
