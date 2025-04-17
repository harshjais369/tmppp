PROMPT_WORD_MATCHER = f"""
Word: distracted
Guess: distracted
Result: True
-
Word: Word: distracted
Guess: distract
Result: True
-
Word: distracted
Guess: distracting
Result: True
-
Word: distracted
Guess: distraction
Result: True
-
Word: distracted
Guess: distract ing ed ion
Result: True
-
Word: distracted
Guess: distro
Result: False
-
Word: distracted
Guess: distractd
Result: True
-
Word: distracted
Guess: distorted
Result: False
-
Word: distracted
Guess: distributed ing ion
Result: False
-
Word: violation
Guess: distracted
Result: False
-
Word: violation
Guess: violates
Result: True
-
Word: violation
Guess: vilation
Result: True
-
Word: violation
Guess: violated ion ing
Result: True
-
Word: properly
Guess: properrrrrty
Result: False
-
Word: properly
Guess: properrrrrly
Result: True
-
Word: properly
Guess: prooperrrrr
Result: True
-
Word: properly
Guess: prosperity
Result: False
-
Word: accomodation
Guess: acco mo date
Result: True
-
Word: accomodation
Guess: akomodayson
Result: True
-
Word: accomodation
Guess: accomodating ed
Result: True
-
Word: peace
Guess: peaceful
Result: True
-
Word: peace
Guess: peacefool
Result: True
-
Word: peace
Guess: peaceless
Result: False
-
Word: peace
Guess: piece
Result: False
-
Word: peace
Guess: peece
Result: True
-
Word: peace
Guess: pace
Result: False
-
Word: peace
Guess: peac
Result: True
-
Word: peace
Guess: pea
Result: False
-
Word: peace
Guess: peeessful
Result: False
-
Word: peace
Guess: peaces
Result: True
-
Word: peace
Guess: peacez
Result: True
-
Word: peace
Guess: pleasee
Result: False
-
Word: destination
Guess: destiny
Result: False
-
Word: destination
Guess: des ti nations
Result: True
-
Word: destination
Guess: dust nation
Result: False
-
Word: destination
Guess: destinasion
Result: True
-
Word: destination
Guess: destiny son
Result: False
-
Word: human
Guess: humanized
Result: True
-
Word: human
Guess: humanity
Result: True
-
Word: human
Guess: hue man
Result: True
-
Word: code
Guess: coding
Result: True
-
Word: code
Guess: program
Result: False
-
Word: code
Guess: cod
Result: True
-
Word: code
Guess: coddfgec
Result: False
-
Word: nevertheless
Guess: nonetheless
Result: False
-
Word: nevertheless
Guess: never the less
Result: True
-
Word: nevertheless
Guess: neverthemore
Result: False
-
Word: shrink
Guess: shk
Result: False
-
Word: shrink
Guess: sink
Result: False
-
Word: shrink
Guess: srink
Result: True
-
Word: shrink
Guess: s h r i n k
Result: True
-
Word: shrink
Guess: she rank
Result: False
-
Word: speciality
Guess: spatial ty
Result: False
-
Word: speciality
Guess: specs litti
Result: False
-
Word: speciality
Guess: specificity
Result: False
-
Word: speciality
Guess: special s ist ity
Result: True
-
Word: speciality
Guess: spclty
Result: False
-
Word: stampede
Guess: stamp
Result: False
-
Word: playstation
Guess: play
Result: False
-
Word: container
Guess: conta
Result: False
-
Word: retirement
Guess: retire
Result: False
-
Word: affected
Guess: affects
Result: True
-
Word: affected
Guess: affection
Result: False
-
Word: affected
Guess: affectionate
Result: False
-
""".strip()
