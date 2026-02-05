import { useState, useEffect } from "react"
import { useTheme } from "@/components/theme-provider"
import { useAuth } from "@/context/AuthContext"
import { ModeToggle } from "@/components/mode-toggle"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"
import OptimizationTab from "@/components/settings/OptimizationTab"
import { screeningCache } from "@/utils/cache"

export default function Settings() {
    const [activeTab, setActiveTab] = useState("appearance")
    const { theme, setTheme } = useTheme()
    const { user } = useAuth()
    const [characters, setCharacters] = useState([])
    const [activeCharacter, setActiveCharacter] = useState("lynch")
    const [characterLoading, setCharacterLoading] = useState(true)
    const [switchingCharacter, setSwitchingCharacter] = useState(false)
    const [expertiseLevel, setExpertiseLevel] = useState("practicing")
    const [expertiseLoading, setExpertiseLoading] = useState(true)
    const [switchingExpertise, setSwitchingExpertise] = useState(false)

    const [algorithmTuningEnabled, setAlgorithmTuningEnabled] = useState(false)

    useEffect(() => {
        // Fetch available characters and current setting
        Promise.all([
            fetch("/api/characters").then(res => res.json()),
            fetch("/api/settings/character", { credentials: 'include' }).then(res => res.json()),
            fetch("/api/settings/expertise-level", { credentials: 'include' }).then(res => res.json()),
            fetch("/api/settings", { cache: 'no-store' }).then(res => res.json())
        ]).then(([charsData, settingData, expertiseData, generalSettings]) => {
            setCharacters(charsData.characters || [])
            setActiveCharacter(settingData.active_character || "lynch")
            setCharacterLoading(false)
            setExpertiseLevel(expertiseData.expertise_level || "practicing")
            setExpertiseLoading(false)

            // Check feature flag
            const algoEnabled = generalSettings.feature_algorithm_optimization_enabled?.value === true ||
                generalSettings.feature_algorithm_optimization_enabled?.value === 'true'
            setAlgorithmTuningEnabled(algoEnabled)
        }).catch(err => {
            console.error("Failed to load settings:", err)
            setCharacterLoading(false)
            setExpertiseLoading(false)
        })
    }, [])

    const handleCharacterChange = async (characterId) => {
        if (switchingCharacter) return // Prevent double-clicks

        setSwitchingCharacter(true)
        try {
            // 1. Save character preference to database
            const response = await fetch("/api/settings/character", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ character_id: characterId }),
                credentials: 'include'
            })

            if (!response.ok) {
                throw new Error('Failed to update character')
            }

            // 2. Update local state
            setActiveCharacter(characterId)

            // 3. Update localStorage so App.jsx picks up the change
            localStorage.setItem('activeCharacter', characterId)

            // Dispatch custom event to notify App.jsx (storage event doesn't fire in same tab)
            window.dispatchEvent(new CustomEvent('characterChanged', {
                detail: { character: characterId }
            }))

            // 4. Clear the screening cache
            await screeningCache.clear()

            // 5. Prefetch fresh data for the new character
            const dataResponse = await fetch(`/api/sessions/latest?limit=10000&character=${characterId}`, {
                credentials: 'include'
            })

            if (dataResponse.ok) {
                const sessionData = await dataResponse.json()

                // 6. Cache the fresh data
                if (user?.id) {
                    await screeningCache.saveResults(user.id, characterId, sessionData)
                }
            }

        } catch (err) {
            console.error("Failed to update character:", err)
            alert('Failed to switch character. Please try again.')
        } finally {
            setSwitchingCharacter(false)
        }
    }

    const handleExpertiseLevelChange = async (level) => {
        if (switchingExpertise) return // Prevent double-clicks

        setSwitchingExpertise(true)
        try {
            const response = await fetch("/api/settings/expertise-level", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ expertise_level: level }),
                credentials: 'include'
            })

            if (!response.ok) {
                throw new Error('Failed to update expertise level')
            }

            // Update local state
            setExpertiseLevel(level)

        } catch (err) {
            console.error("Failed to update expertise level:", err)
            alert('Failed to update expertise level. Please try again.')
        } finally {
            setSwitchingExpertise(false)
        }
    }

    const sidebarItems = [
        {
            id: "appearance",
            title: "Appearance",
        },
        {
            id: "character",
            title: "Investment Style",
        },
        {
            id: "expertise",
            title: "Expertise Level",
        },
        ...(algorithmTuningEnabled ? [{
            id: "item2",
            title: "Algorithm Tuning",
        }] : []),
    ]

    return (
        <div className="space-y-6 p-10 pb-16 block">
            <div className="space-y-0.5">
                <h2 className="text-2xl font-bold tracking-tight">Settings</h2>
                <p className="text-muted-foreground">
                    Manage your account settings and preferences.
                </p>
            </div>
            <div className="border-t my-6" />
            <div className="flex flex-col space-y-8 lg:flex-row lg:space-x-12 lg:space-y-0">
                <aside className="-mx-4 lg:w-1/5">
                    <nav className="flex space-x-2 lg:flex-col lg:space-x-0 lg:space-y-1">
                        {sidebarItems.map((item) => (
                            <Button
                                key={item.id}
                                variant="ghost"
                                className={cn(
                                    "justify-start hover:bg-muted font-normal",
                                    activeTab === item.id && "bg-muted hover:bg-muted font-medium"
                                )}
                                onClick={() => setActiveTab(item.id)}
                            >
                                {item.title}
                            </Button>
                        ))}
                    </nav>
                </aside>
                <div className="flex-1 lg:max-w-4xl">
                    {activeTab === "appearance" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Appearance</h3>
                                <p className="text-sm text-muted-foreground">
                                    Customize the look and feel of the application. Automatically switch between day and night themes.
                                </p>
                            </div>
                            <div className="border-t" />
                            <Card>
                                <CardHeader>
                                    <CardTitle>Theme</CardTitle>
                                    <CardDescription>
                                        Select the theme for the app.
                                    </CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <RadioGroup
                                        defaultValue={theme}
                                        onValueChange={(value) => setTheme(value)}
                                        className="gap-4"
                                    >
                                        <div className="flex items-center gap-3 space-x-0">
                                            <RadioGroupItem value="light" id="light" />
                                            <Label htmlFor="light">Light</Label>
                                        </div>
                                        <div className="flex items-center gap-3 space-x-0">
                                            <RadioGroupItem value="dark" id="dark" />
                                            <Label htmlFor="dark">Dark</Label>
                                        </div>
                                        <div className="flex items-center gap-3 space-x-0">
                                            <RadioGroupItem value="system" id="system" />
                                            <Label htmlFor="system">System</Label>
                                        </div>
                                    </RadioGroup>
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "item2" && (
                        <OptimizationTab />
                    )}

                    {activeTab === "character" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Investment Style</h3>
                                <p className="text-sm text-muted-foreground">
                                    Choose your investment philosophy. This affects how stocks are analyzed, scored, and discussed.
                                </p>
                            </div>
                            <div className="border-t" />
                            <Card>
                                <CardHeader>
                                    <CardTitle>Investment Character</CardTitle>
                                    <CardDescription>
                                        Each character has a unique approach to evaluating stocks.
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="relative">
                                    {switchingCharacter && (
                                        <div className="absolute inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center z-10 rounded-lg">
                                            <div className="flex flex-col items-center gap-2">
                                                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                                                <p className="text-sm text-muted-foreground">Switching character...</p>
                                            </div>
                                        </div>
                                    )}
                                    {characterLoading ? (
                                        <div className="text-muted-foreground">Loading...</div>
                                    ) : (
                                        <RadioGroup
                                            value={activeCharacter}
                                            onValueChange={handleCharacterChange}
                                            className="gap-4"
                                            disabled={switchingCharacter}
                                        >
                                            {characters.map((char) => (
                                                <div key={char.id} className="flex items-start gap-3 space-x-0">
                                                    <RadioGroupItem
                                                        value={char.id}
                                                        id={char.id}
                                                        className="mt-1"
                                                        disabled={switchingCharacter}
                                                    />
                                                    <div className="flex flex-col">
                                                        <Label htmlFor={char.id} className="font-medium cursor-pointer">
                                                            {char.name}
                                                        </Label>
                                                        <span className="text-sm text-muted-foreground">
                                                            {char.description}
                                                        </span>
                                                    </div>
                                                </div>
                                            ))}

                                            {/* Coming Soon Characters */}
                                            {[
                                                { id: 'munger', name: 'Charlie Munger', description: 'Multidisciplinary thinking and focusing on high-quality businesses with strong moats.' },
                                                { id: 'graham', name: 'Benjamin Graham', description: 'Deep value investing, margin of safety, and net-net analysis.' },
                                                { id: 'dalio', name: 'Ray Dalio', description: 'Principles-based macro analysis and radical transparency.' }
                                            ].map((char) => (
                                                <div key={char.id} className="flex items-start gap-3 space-x-0 opacity-60">
                                                    <RadioGroupItem
                                                        value={char.id}
                                                        id={char.id}
                                                        className="mt-1"
                                                        disabled={true}
                                                    />
                                                    <div className="flex flex-col">
                                                        <Label htmlFor={char.id} className="font-medium">
                                                            {char.name} <span className="text-xs font-normal">(Coming Soon)</span>
                                                        </Label>
                                                        <span className="text-sm text-muted-foreground">
                                                            {char.description}
                                                        </span>
                                                    </div>
                                                </div>
                                            ))}
                                        </RadioGroup>
                                    )}
                                </CardContent>
                            </Card>
                        </div>
                    )}

                    {activeTab === "expertise" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Expertise Level</h3>
                                <p className="text-sm text-muted-foreground">
                                    Choose your investing expertise level. This adjusts how analyses and conversations are communicated to match your knowledge.
                                </p>
                            </div>
                            <div className="border-t" />
                            <Card>
                                <CardHeader>
                                    <CardTitle>Communication Style</CardTitle>
                                    <CardDescription>
                                        Select how technical and detailed you want the analysis to be.
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="relative">
                                    {switchingExpertise && (
                                        <div className="absolute inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center z-10 rounded-lg">
                                            <div className="flex flex-col items-center gap-2">
                                                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                                                <p className="text-sm text-muted-foreground">Updating expertise level...</p>
                                            </div>
                                        </div>
                                    )}
                                    {expertiseLoading ? (
                                        <div className="text-muted-foreground">Loading...</div>
                                    ) : (
                                        <RadioGroup
                                            value={expertiseLevel}
                                            onValueChange={handleExpertiseLevelChange}
                                            className="gap-4"
                                            disabled={switchingExpertise}
                                        >
                                            <div className="flex items-start gap-3 space-x-0">
                                                <RadioGroupItem
                                                    value="learning"
                                                    id="learning"
                                                    className="mt-1"
                                                    disabled={switchingExpertise}
                                                />
                                                <div className="flex flex-col">
                                                    <Label htmlFor="learning" className="font-medium cursor-pointer">
                                                        Learning
                                                    </Label>
                                                    <span className="text-sm text-muted-foreground">
                                                        I'm learning to invest. Help educate me and use simpler terms with clear explanations.
                                                    </span>
                                                </div>
                                            </div>
                                            <div className="flex items-start gap-3 space-x-0">
                                                <RadioGroupItem
                                                    value="practicing"
                                                    id="practicing"
                                                    className="mt-1"
                                                    disabled={switchingExpertise}
                                                />
                                                <div className="flex flex-col">
                                                    <Label htmlFor="practicing" className="font-medium cursor-pointer">
                                                        Practicing
                                                    </Label>
                                                    <span className="text-sm text-muted-foreground">
                                                        I understand the basics and want to deepen my knowledge with more nuanced analysis.
                                                    </span>
                                                </div>
                                            </div>
                                            <div className="flex items-start gap-3 space-x-0">
                                                <RadioGroupItem
                                                    value="expert"
                                                    id="expert"
                                                    className="mt-1"
                                                    disabled={switchingExpertise}
                                                />
                                                <div className="flex flex-col">
                                                    <Label htmlFor="expert" className="font-medium cursor-pointer">
                                                        Expert
                                                    </Label>
                                                    <span className="text-sm text-muted-foreground">
                                                        I'm a seasoned investor. Use technical language and focus on unique insights.
                                                    </span>
                                                </div>
                                            </div>
                                        </RadioGroup>
                                    )}
                                </CardContent>
                            </Card>
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}

