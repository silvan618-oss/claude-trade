import re
def describe(text, mapping):
    """Replace @NAME (and Peter) outside spoken lines with appearance descriptions."""
    parts=text.split('"')
    for i in range(0,len(parts),2):
        p=parts[i]
        for name,(desc,poss) in mapping.items():
            p=re.sub(r"@"+name+r"'s\b", poss, p)
            p=re.sub(r"@"+name+r"\b", desc, p)
        p=p.replace("Peter, the short chubby blond boy,","the short chubby blond boy")
        p=re.sub(r"\bPeter's\b","the chubby blond boy's",p)
        p=re.sub(r"\bPeter\b","the chubby blond boy",p)
        # sentence starts
        p=re.sub(r"(^|\. |, then |Then )the ", lambda m: m.group(1)+("The " if m.group(1) in ("",". ") else "the "), p)
        parts[i]=p
    return '"'.join(parts)
MAR={"PRONGS":("the boy with round glasses and messy black hair","the boy with round glasses'"),
     "PADFOOT":("the boy with long dark hair","the long-haired boy's"),
     "MOONY":("the boy with short sandy hair","the sandy-haired boy's"),
     "EVANS":("the girl with long red hair","the red-haired girl's")}
