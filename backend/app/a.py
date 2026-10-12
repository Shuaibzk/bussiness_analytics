def palli(a):
    b = ""
    for index in range(len(a)):
        if a[index] == " ":
            continue 
        b += a[index]

    i = 0
    j = len(b) - 1

    while i < j:
        if b[i] != b[j]:
            return False

        i += 1
        j -= 1

    return True 


def substring(text):
    a = ""

    for i in range(len(text)):
        b = ""
        for j in range(i, len(text)):
            if b[j] in a:
                break 

            b += text[j]
            a = b

    return a
 
print(palli("race a car"))
# substring("pwwkew")