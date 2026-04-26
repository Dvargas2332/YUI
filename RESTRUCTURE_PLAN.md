# Calculadora Científica Avanzada en Python

import math

# ==================== OPERACIONES BÁSICAS ====================

def suma(a, b):
    return a + b

def resta(a, b):
    return a - b

def multiplicacion(a, b):
    return a * b

def division(a, b):
    if b == 0:
        return "Error: división por cero"
    return a / b

# ==================== ECUACIONES ====================

def ecuacion_primer_grado(a, b):
    """Resuelve ax + b = 0"""
    if a == 0:
        if b == 0:
            return "Infinitas soluciones (0 = 0)"
        return "Sin solución (contradicción)"
    x = -b / a
    return f"x = {x}"

def ecuacion_segundo_grado(a, b, c):
    """Resuelve ax² + bx + c = 0"""
    if a == 0:
        return ecuacion_primer_grado(b, c)

    discriminante = b**2 - 4*a*c

    if discriminante > 0:
        x1 = (-b + math.sqrt(discriminante)) / (2 * a)
        x2 = (-b - math.sqrt(discriminante)) / (2 * a)
        return f"Discriminante = {discriminante}\nx1 = {x1}\nx2 = {x2}"
    elif discriminante == 0:
        x = -b / (2 * a)
        return f"Discriminante = 0\nRaíz doble: x = {x}"
    else:
        real = -b / (2 * a)
        imag = math.sqrt(abs(discriminante)) / (2 * a)
        return f"Discriminante = {discriminante}\nx1 = {real} + {imag}i\nx2 = {real} - {imag}i"

# ==================== ALGORITMOS ====================

def mcd(a, b):
    """Máximo común divisor (Euclides)"""
    a, b = abs(int(a)), abs(int(b))
    while b:
        a, b = b, a % b
    return a

def mcm(a, b):
    """Mínimo común múltiplo"""
    return abs(int(a) * int(b)) // mcd(a, b)

def factorial(n):
    """Factorial iterativo"""
    n = int(n)
    if n < 0:
        return "Error: factorial de número negativo"
    resultado = 1
    for i in range(2, n + 1):
        resultado *= i
    return resultado

def fibonacci(n):
    """Serie de Fibonacci hasta n términos"""
    n = int(n)
    if n <= 0:
        return []
    if n == 1:
        return [0]
    serie = [0, 1]
    for _ in range(2, n):
        serie.append(serie[-1] + serie[-2])
    return serie

def es_primo(n):
    """Verifica si un número es primo"""
    n = int(n)
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True

def criba_eratostenes(limite):
    """Genera primos hasta un límite"""
    limite = int(limite)
    if limite < 2:
        return []
    primos = [True] * (limite + 1)
    primos[0] = primos[1] = False
    for i in range(2, int(math.sqrt(limite)) + 1):
        if primos[i]:
            for j in range(i*i, limite +