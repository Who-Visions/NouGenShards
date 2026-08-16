# Local Scoped Code Example

This demonstrates a `LOCAL_SCOPED_CODE` task routed to Gemma 4 E2B locally.

## Task Input
```text
Refactor the following function to use a list comprehension and return only the squares of even numbers.
```

## Input Code
```python
def get_even_squares(numbers):
    result = []
    for n in numbers:
        if n % 2 == 0:
            result.append(n ** 2)
    return result
```

## Generated Output
```python
def get_even_squares(numbers):
    return [n ** 2 for n in numbers if n % 2 == 0]
```
