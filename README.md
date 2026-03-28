# yhack-2026

Puzzle contains:
-Script to generate input file
-Program to convert input file to output file
-Human description of what the program does

AI is prompted to generate puzzle
Theme and difficulty -> Openai api call -> puzzle

Account with auth, guest mode
ELO system, Zen mode, multiplayer mode
Multiplayer mode has casual and ranked mode:
Multiplayer has shareable link and people can join (no automatchmaking yet). Everyone must be logged in for it to be ranked mode. Otherwise, it must be casual. 
In zen mode and casual multiplayer, no ELO system, party leader can customize theme and difficulty and time limit.

Game idea:
Users are shown a sample input and corresponding output
They can code in python in an online editor. when they submit their code for judging it should first run on the sample cases and then run on the script-generated bigger input file. users can ask for hints if they cant figure out the human description of the program they're trying to write. But in ranked this will affect their elo calculation.
what goes into elo calculation: current elo, everyone else's elo, difficulty of problem, order of solving, time took to solve, partial credit (passed some test cases but not all), some other factors i may have forgotten.

Technologies:
-Python flask backend
-Sandboxing for code judging (e.g. snekbox)
-Svelte typescript frontend
-Tailwindcss
