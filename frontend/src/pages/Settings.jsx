import { useState, useEffect } from "react"
import { useTheme } from "@/components/theme-provider"
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
    const [characters, setCharacters] = useState([])
    const [activeCharacter, setActiveCharacter] = useState("lynch")
    const [characterLoading, setCharacterLoading] = useState(true)

    useEffect(() => {
        // Fetch available characters and current setting
        Promise.all([
            fetch("/api/characters").then(res => res.json()),
            fetch("/api/settings/character", { credentials: 'include' }).then(res => res.json())
        ]).then(([charsData, settingData]) => {
            setCharacters(charsData.characters || [])
            setActiveCharacter(settingData.active_character || "lynch")
            setCharacterLoading(false)
        }).catch(err => {
            console.error("Failed to load characters:", err)
            setCharacterLoading(false)
        })
    }, [])

    const handleCharacterChange = async (characterId) => {
        try {
            const response = await fetch("/api/settings/character", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ character_id: characterId }),
                credentials: 'include'
            })
            if (response.ok) {
                setActiveCharacter(characterId)
                // Update localStorage so App.jsx picks up the change
                localStorage.setItem('activeCharacter', characterId)
                // Clear the screening cache to force fresh data fetch for new character
                await screeningCache.clear()
                console.log('[Settings] Cleared screening cache after character switch to', characterId)
            }
        } catch (err) {
            console.error("Failed to update character:", err)
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
            id: "item2",
            title: "Algorithm Tuning",
        },
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
                                <CardContent>
                                    {characterLoading ? (
                                        <div className="text-muted-foreground">Loading...</div>
                                    ) : (
                                        <RadioGroup
                                            value={activeCharacter}
                                            onValueChange={handleCharacterChange}
                                            className="gap-4"
                                        >
                                            {characters.map((char) => (
                                                <div key={char.id} className="flex items-start gap-3 space-x-0">
                                                    <RadioGroupItem value={char.id} id={char.id} className="mt-1" />
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

