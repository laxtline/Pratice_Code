"""Language templates, local filenames and runtime availability."""
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent
LANGUAGES = {
 'python':dict(name='Python',filename='main.py',mode='python',runtime='python',code='# Online Python compiler (interpreter)\n# Write and run Python using this editor.\n\nprint("Hello, world!")\n'),
 'r':dict(name='R',filename='main.R',mode='r',runtime='Rscript',code='# Write and run R code\nmessage <- "Hello, world!"\nprint(message)\n'),
 'sql':dict(name='SQL',filename='main.sql',mode='text/x-sql',runtime='sqlite',code='-- SQLite: edit a query and select Run\nCREATE TABLE students (id INTEGER, name TEXT);\nINSERT INTO students VALUES (1, \'Surya\'), (2, \'Alex\');\nSELECT * FROM students;\n'),
 'html':dict(name='HTML/CSS',filename='index.html',mode='htmlmixed',runtime='browser',code='<!doctype html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8">\n  <meta name="viewport" content="width=device-width,initial-scale=1">\n  <title>My local page</title>\n  <style>\n    body { font-family: system-ui; padding: 40px; color: #25265e; }\n    button { background: #0556f3; color: white; border: 0; padding: 12px 20px; border-radius: 6px; cursor: pointer; }\n  </style>\n</head>\n<body>\n  <h1>Hello, world!</h1>\n  <p>Edit this code to see your live preview.</p>\n  <button onclick="this.textContent = \'It works!\'">Click me</button>\n</body>\n</html>\n'),
 'java':dict(name='Java',filename='Main.java',mode='text/x-java',runtime='java',code='public class Main {\n    public static void main(String[] args) {\n        System.out.println("Hello, world!");\n    }\n}\n'),
 'kotlin':dict(name='Kotlin',filename='main.kt',mode='text/x-kotlin',runtime='kotlinc',code='fun main() {\n    println("Hello, world!")\n}\n'),
 'c':dict(name='C',filename='main.c',mode='text/x-csrc',runtime='gcc',code='#include <stdio.h>\n\nint main(void) {\n    printf("Hello, world!\\n");\n    return 0;\n}\n'),
 'cpp':dict(name='C++',filename='main.cpp',mode='text/x-c++src',runtime='g++',code='#include <iostream>\n\nint main() {\n    std::cout << "Hello, world!" << std::endl;\n    return 0;\n}\n'),
 'csharp':dict(name='C#',filename='Main.cs',mode='text/x-csharp',runtime='dotnet',code='using System;\n\nclass Program {\n    static void Main() {\n        Console.WriteLine("Hello, world!");\n    }\n}\n'),
 'javascript':dict(name='JavaScript',filename='main.js',mode='javascript',runtime='node',code='// JavaScript runs locally using Node.js\nconsole.log("Hello, world!");\n'),
 'typescript':dict(name='TypeScript',filename='main.ts',mode='text/typescript',runtime='node',code='// TypeScript runs locally using Node.js type stripping\nconst message: string = "Hello, world!";\nconsole.log(message);\n'),
 'golang':dict(name='Go',filename='main.go',mode='go',runtime='go',code='package main\n\nimport "fmt"\n\nfunc main() {\n    fmt.Println("Hello, world!")\n}\n'),
 'rust':dict(name='Rust',filename='main.rs',mode='rust',runtime='rustc',code='fn main() {\n    println!("Hello, world!");\n}\n'),
 'scala':dict(name='Scala',filename='main.scala',mode='text/x-scala',runtime='scala',code='object Main extends App {\n    println("Hello, world!")\n}\n'),
 'dart':dict(name='Dart',filename='main.dart',mode='dart',runtime='dart',code='void main() {\n  print("Hello, world!");\n}\n'),
 'ruby':dict(name='Ruby',filename='main.rb',mode='ruby',runtime='ruby',code='# Write and run Ruby code\nputs "Hello, world!"\n'),
 'php':dict(name='PHP',filename='main.php',mode='application/x-httpd-php',runtime='php',code='<?php\necho "Hello, world!\\n";\n'),
 'swift':dict(name='Swift',filename='main.swift',mode='swift',runtime='swift',code='// Write and run Swift code\nprint("Hello, world!")\n')
}

def command_path(language):
    config = LANGUAGES[language]
    if config['runtime'] in ('python','sqlite','browser'):
        return sys.executable
    path = shutil.which(config['runtime'])
    # dotnet runtime alone cannot compile C#; use an installed C# compiler only.
    if language == 'csharp':
        return shutil.which('csc') or shutil.which('mcs')
    return path

def manifest():
    result = []
    for key,config in LANGUAGES.items():
        available = bool(command_path(key))
        result.append(dict(id=key,**config,available=available,
            note=None if available else f"{config['name']} runtime is not installed. Install {config['runtime']} and restart this server to run this language. Code editing, saving and download work now."))
    return result
