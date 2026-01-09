import { useState } from "react"
import { useTheme } from "@/components/theme-provider"
import { ModeToggle } from "@/components/mode-toggle"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"
import OptimizationTab from "@/components/settings/OptimizationTab"

export default function Settings() {
    const [activeTab, setActiveTab] = useState("appearance")
    const { theme, setTheme } = useTheme()

    const sidebarItems = [
        {
            id: "appearance",
            title: "Appearance",
        },
        {
            id: "item2",
            title: "Algorithm Tuning",
        },
        {
            id: "item3",
            title: "Item 3",
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

                    {activeTab === "item3" && (
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-medium">Item 3</h3>
                                <p className="text-sm text-muted-foreground">
                                    This is a placeholder for Item 3 settings.
                                </p>
                            </div>
                            <div className="border-t" />
                            <div className="flex items-center justify-center h-40 border-2 border-dashed rounded-lg text-muted-foreground">
                                Content for Item 3
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}

