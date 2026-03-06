from siftout import Janitor 

cleaner = Janitor(extra_patterns=["*.bak"])
report = cleaner.self_destruct()
print(f"Cleaner Report: {report}") 

cleaner.secure_env()
print("Environment Secured")
