'''
	graph.py v1.0.1 by Mark Cockburn <mork@themork.co.uk>
'''

def draw (data=[],height=10,find=lambda d: d):
    if data == []:
        return ''

    string = ''

    largest = 0
    for x in data:
        if find(x) > largest:
            largest = find(x)

    for y in range(height,0,-1):
        for x in data:
            if round(find(x) / largest * height) >= y:
                string += '█'*len(str(find(x))) + ' '
            else:
                string += ' '*len(str(find(x))) + ' '
        string += '\n'

    for x in data:
        string += str(find(x)) + ' '
    string += '\n'

    return string

