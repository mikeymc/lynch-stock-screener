// ABOUTME: Multi-step onboarding wizard for new users
// ABOUTME: Collects expertise level, character preference, and theme settings

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useTheme } from './theme-provider'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from './ui/dialog'
import { Button } from './ui/button'
import { RadioGroup, RadioGroupItem } from './ui/radio-group'
import { Label } from './ui/label'

const STEPS = {
    EXPERTISE: 1,
    CHARACTER: 2,
    THEME: 3,
    CONFIRMATION: 4,
}

const EXPERTISE_LEVELS = [
    {
        id: 'learning',
        name: 'Learning',
        description: 'I am new to investing and want to build a solid foundation.',
    },
    {
        id: 'practicing',
        name: 'Practicing',
        description: 'I have a working knowledge of investing and want to deepen my understanding.',
    },
    {
        id: 'expert',
        name: 'Expert',
        description: 'I am comfortable with complex finance concepts and investing terminology.',
    },
]

const THEME_OPTIONS = [
    {
        id: 'light',
        name: 'Light',
        description: 'Clean, bright interface',
    },
    {
        id: 'dark',
        name: 'Dark',
        description: 'Good for low-light environments',
    },
    {
        id: 'system',
        name: 'System',
        description: 'Match your device settings',
    },
]

export function OnboardingWizard({ open, onComplete, onSkip }) {
    const [currentStep, setCurrentStep] = useState(STEPS.EXPERTISE)
    const [selections, setSelections] = useState({
        expertise: 'practicing', // default
        character: 'lynch', // default
        theme: 'system', // default
    })
    const [characters, setCharacters] = useState([])
    const [loading, setLoading] = useState(false)
    const [charactersLoading, setCharactersLoading] = useState(true)

    const navigate = useNavigate()
    const { user, checkAuth } = useAuth()
    const { setTheme } = useTheme()

    // Fetch available characters
    useEffect(() => {
        const fetchCharacters = async () => {
            try {
                const response = await fetch('/api/characters')
                const data = await response.json()
                setCharacters(data.characters || [])
            } catch (error) {
                console.error('Failed to fetch characters:', error)
            } finally {
                setCharactersLoading(false)
            }
        }

        if (open) {
            fetchCharacters()
        }
    }, [open])

    const handleNext = () => {
        if (currentStep < STEPS.CONFIRMATION) {
            setCurrentStep(currentStep + 1)
        } else {
            handleComplete()
        }
    }

    const handleBack = () => {
        if (currentStep > STEPS.EXPERTISE) {
            setCurrentStep(currentStep - 1)
        }
    }

    const handleComplete = async (goToHelp = false) => {
        setLoading(true)
        try {
            // Save expertise level
            await fetch('/api/settings/expertise-level', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ expertise_level: selections.expertise }),
            })

            // Save character preference
            await fetch('/api/settings/character', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ character_id: selections.character }),
            })

            // Update localStorage for character
            localStorage.setItem('activeCharacter', selections.character)
            window.dispatchEvent(new CustomEvent('characterChanged', {
                detail: { character: selections.character }
            }))

            // Save theme
            await fetch('/api/settings/theme', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ theme: selections.theme }),
            })
            setTheme(selections.theme)

            // Mark onboarding as complete
            await fetch('/api/user/complete_onboarding', {
                method: 'POST',
                credentials: 'include',
            })

            // Refresh auth state
            await checkAuth()

            // Navigate to help page if requested
            if (goToHelp) {
                navigate('/help')
            }

            // Call completion callback
            if (onComplete) {
                onComplete()
            }
        } catch (error) {
            console.error('Failed to complete onboarding:', error)
        } finally {
            setLoading(false)
        }
    }

    const handleSkip = async () => {
        setLoading(true)
        try {
            // Just mark onboarding as complete without changing settings
            await fetch('/api/user/complete_onboarding', {
                method: 'POST',
                credentials: 'include',
            })
            await checkAuth()

            if (onSkip) {
                onSkip()
            }
        } catch (error) {
            console.error('Failed to skip onboarding:', error)
        } finally {
            setLoading(false)
        }
    }

    const updateSelection = (key, value) => {
        setSelections(prev => ({ ...prev, [key]: value }))
    }

    const getCharacterName = (id) => {
        const char = characters.find(c => c.id === id)
        return char ? char.name : id
    }

    const getExpertiseName = (id) => {
        const level = EXPERTISE_LEVELS.find(l => l.id === id)
        return level ? level.name : id
    }

    const getThemeName = (id) => {
        const theme = THEME_OPTIONS.find(t => t.id === id)
        return theme ? theme.name : id
    }

    return (
        <Dialog open={open} onOpenChange={() => { }}>
            <DialogContent className="sm:max-w-[600px]" hideClose>
                {/* Progress dots */}
                <div className="flex justify-center gap-2 mb-4">
                    {[1, 2, 3, 4].map((step) => (
                        <div
                            key={step}
                            className={`h-2 w-2 rounded-full transition-colors ${step === currentStep
                                ? 'bg-primary'
                                : step < currentStep
                                    ? 'bg-primary/50'
                                    : 'bg-muted'
                                }`}
                        />
                    ))}
                </div>

                {/* Step 1: Expertise Level */}
                {currentStep === STEPS.EXPERTISE && (
                    <>
                        <DialogHeader>
                            <DialogTitle>What is your expertise level?</DialogTitle>
                            <DialogDescription>
                                This helps us tailor the interaction style of written analyses and chat responses.
                            </DialogDescription>
                        </DialogHeader>

                        <RadioGroup
                            value={selections.expertise}
                            onValueChange={(value) => updateSelection('expertise', value)}
                            className="gap-4 mt-4"
                        >
                            {EXPERTISE_LEVELS.map((level) => (
                                <div key={level.id} className="flex items-start gap-3 space-x-0">
                                    <RadioGroupItem
                                        value={level.id}
                                        id={`expertise-${level.id}`}
                                        className="mt-1"
                                    />
                                    <div className="flex flex-col">
                                        <Label htmlFor={`expertise-${level.id}`} className="font-medium cursor-pointer">
                                            {level.name}
                                        </Label>
                                        <span className="text-sm text-muted-foreground">
                                            {level.description}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </RadioGroup>

                        <div className="flex justify-end mt-6">
                            <div className="flex gap-2">
                                <Button variant="ghost" onClick={handleSkip} disabled={loading}>
                                    Skip for now
                                </Button>
                                <Button onClick={handleNext} disabled={loading}>
                                    Next
                                </Button>
                            </div>
                        </div>
                    </>
                )}

                {/* Step 2: Character Selection */}
                {currentStep === STEPS.CHARACTER && (
                    <>
                        <DialogHeader>
                            <DialogTitle>Choose your investment philosophy</DialogTitle>
                            <DialogDescription>
                                This shapes the scoring algorithm, investment thesis, chart analysis, and chat responses.
                            </DialogDescription>
                        </DialogHeader>

                        {charactersLoading ? (
                            <div className="flex justify-center py-8">
                                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                            </div>
                        ) : (
                            <RadioGroup
                                value={selections.character}
                                onValueChange={(value) => updateSelection('character', value)}
                                className="gap-4 mt-4"
                            >
                                {characters.map((char) => (
                                    <div key={char.id} className="flex items-start gap-3 space-x-0">
                                        <RadioGroupItem
                                            value={char.id}
                                            id={`char-${char.id}`}
                                            className="mt-1"
                                        />
                                        <div className="flex flex-col">
                                            <Label htmlFor={`char-${char.id}`} className="font-medium cursor-pointer">
                                                {char.name}
                                            </Label>
                                            <span className="text-sm text-muted-foreground">
                                                {char.description}
                                            </span>
                                        </div>
                                    </div>
                                ))}
                            </RadioGroup>
                        )}

                        <div className="flex justify-between mt-6">
                            <Button variant="outline" onClick={handleBack} disabled={loading}>
                                Back
                            </Button>
                            <div className="flex gap-2">
                                <Button variant="ghost" onClick={handleSkip} disabled={loading}>
                                    Skip for now
                                </Button>
                                <Button onClick={handleNext} disabled={loading || charactersLoading}>
                                    Next
                                </Button>
                            </div>
                        </div>
                    </>
                )}

                {/* Step 3: Theme Selection */}
                {currentStep === STEPS.THEME && (
                    <>
                        <DialogHeader>
                            <DialogTitle>Choose your theme</DialogTitle>
                            <DialogDescription>
                                Select your preferred theme.
                            </DialogDescription>
                        </DialogHeader>

                        <RadioGroup
                            value={selections.theme}
                            onValueChange={(value) => updateSelection('theme', value)}
                            className="gap-4 mt-4"
                        >
                            {THEME_OPTIONS.map((theme) => (
                                <div key={theme.id} className="flex items-start gap-3 space-x-0">
                                    <RadioGroupItem
                                        value={theme.id}
                                        id={`theme-${theme.id}`}
                                        className="mt-1"
                                    />
                                    <div className="flex flex-col">
                                        <Label htmlFor={`theme-${theme.id}`} className="font-medium cursor-pointer">
                                            {theme.name}
                                        </Label>
                                        <span className="text-sm text-muted-foreground">
                                            {theme.description}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </RadioGroup>

                        <div className="flex justify-between mt-6">
                            <Button variant="outline" onClick={handleBack} disabled={loading}>
                                Back
                            </Button>
                            <div className="flex gap-2">
                                <Button variant="ghost" onClick={handleSkip} disabled={loading}>
                                    Skip for now
                                </Button>
                                <Button onClick={handleNext} disabled={loading}>
                                    Next
                                </Button>
                            </div>
                        </div>
                    </>
                )}

                {/* Step 4: Confirmation */}
                {currentStep === STEPS.CONFIRMATION && (
                    <>
                        <DialogHeader>
                            <DialogTitle>Settings</DialogTitle>
                        </DialogHeader>

                        <div className="mt-4 p-4 bg-muted rounded-lg space-y-2">
                            <ul className="text-sm text-muted-foreground space-y-1">
                                <li>
                                    <span className="font-medium">Expertise Level:</span> {getExpertiseName(selections.expertise)}
                                </li>
                                <li>
                                    <span className="font-medium">Investment Philosophy:</span> {getCharacterName(selections.character)}
                                </li>
                                <li>
                                    <span className="font-medium">Theme:</span> {getThemeName(selections.theme)}
                                </li>
                            </ul>
                        </div>
                        <p className="text-sm text-muted-foreground mt-3">
                            Check out the quickstart guide to get started!
                        </p>


                        <div className="flex justify-between mt-6">
                            <Button variant="outline" onClick={handleBack} disabled={loading}>
                                Back
                            </Button>
                            <div className="flex gap-2">
                                <Button variant="outline" onClick={() => handleComplete(false)} disabled={loading}>
                                    {loading ? (
                                        <>
                                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary mr-2"></div>
                                            Setting up...
                                        </>
                                    ) : (
                                        'Let me explore'
                                    )}
                                </Button>
                                <Button onClick={() => handleComplete(true)} disabled={loading}>
                                    {loading ? (
                                        <>
                                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                                            Setting up...
                                        </>
                                    ) : (
                                        'Show Quick Start Guide'
                                    )}
                                </Button>
                            </div>
                        </div>
                    </>
                )}
            </DialogContent>
        </Dialog>
    )
}
