import re

new_html_content = """<main class="flex-grow pt-32 lg:pt-48">
            <section class="max-w-7xl mx-auto px-6 lg:px-8 pb-32 overflow-hidden">
                <div class="flex flex-col md:flex-row justify-between items-end gap-16 relative">
                    <!-- Decorative Background Element -->
                    <div class="absolute -top-24 -left-20 w-64 h-64 bg-accent-bronze/5 rounded-full blur-[100px] pointer-events-none"></div>
                    
                    <div class="max-w-4xl relative z-10">
                        <div class="flex items-center gap-4 mb-8 reveal reveal-up stagger-1">
                            <span class="w-12 h-px bg-accent-bronze/40"></span>
                            <span class="text-accent-bronze text-[10px] uppercase tracking-[0.5em] font-bold">Services</span>
                        </div>
                        <h1 class="font-serif text-5xl md:text-8xl lg:text-9xl text-ivory font-light leading-[1.05] tracking-tight mb-10 reveal reveal-up stagger-2" data-cms="specimens/hero/title">
                            Curated <br />
                            <span class="text-accent-bronze italic font-light drop-shadow-sm">Specimens</span>
                        </h1>
                    </div>
                    <div class="flex flex-col items-start md:items-end gap-8 max-w-xs mb-6 reveal reveal-up stagger-3">
                        <p class="text-gray-400 font-light text-sm leading-relaxed uppercase tracking-[0.2em] text-left md:text-right border-l md:border-l-0 md:border-r border-accent-bronze/30 pl-8 md:pl-0 md:pr-8" data-cms="specimens/hero/subtitle">
                            Not added — introduced. Every specimen placed with purpose.
                        </p>
                        <div class="h-px w-20 bg-gradient-to-r md:bg-gradient-to-l from-accent-bronze/60 to-transparent"></div>
                    </div>
                </div>
            </section>

            <section class="pb-32 px-6 lg:px-24 flex flex-col gap-24 lg:gap-32 w-full max-w-7xl mx-auto">

                <!-- Block 1: Image Left, Text Right -->
                <div class="flex flex-col lg:flex-row items-center gap-12 lg:gap-20">
                    <div class="w-full lg:w-[45%] h-64 lg:h-96 bg-surface-dark relative border border-white/5 overflow-hidden group flex-shrink-0">
                        <img src="https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_1.png" alt="Sensory Calm" class="absolute inset-0 w-full h-full object-cover transition-transform duration-1000 group-hover:scale-105" data-cms="specimens/block1/image" />
                    </div>
                    <div class="w-full lg:w-[55%] flex flex-col justify-center">
                        <div class="w-12 h-px bg-accent-bronze mb-6"></div>
                        <h3 class="font-serif text-2xl text-ivory mb-6 font-medium" data-cms="specimens/block1/title">Sensory Calm</h3>
                        <p class="text-ivory-dim font-light leading-relaxed text-sm md:text-base" data-cms="specimens/block1/body">
                            Golden light, water reflections, and a sculptural specimen create sensory calm — where negative ions, natural textures, and biophilic balance reduce stress, slow the mind, and elevate the entire outdoor experience.
                        </p>
                    </div>
                </div>

                <!-- Block 2: Text Left, Image Right -->
                <div class="flex flex-col lg:flex-row-reverse items-center gap-12 lg:gap-20">
                    <div class="w-full lg:w-[45%] h-64 lg:h-96 bg-surface-dark relative border border-white/5 overflow-hidden group flex-shrink-0">
                        <img src="https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_2.png" alt="Breathable Living" class="absolute inset-0 w-full h-full object-cover transition-transform duration-1000 group-hover:scale-105" data-cms="specimens/block2/image" />
                    </div>
                    <div class="w-full lg:w-[55%] flex flex-col justify-center lg:items-start lg:text-left">
                        <div class="w-12 h-px bg-accent-bronze mb-6"></div>
                        <h3 class="font-serif text-2xl text-ivory mb-6 font-medium" data-cms="specimens/block2/title">Breathable Living</h3>
                        <p class="text-ivory-dim font-light leading-relaxed text-sm md:text-base" data-cms="specimens/block2/body">
                            Expansive light, open flow, and a single curated plant enhance oxygen levels and visual calm — proven to reduce cortisol and improve focus, creating a breathable, emotionally warm living environment.
                        </p>
                    </div>
                </div>

                <!-- Block 3: Image Left, Text Right -->
                <div class="flex flex-col lg:flex-row items-center gap-12 lg:gap-20">
                    <div class="w-full lg:w-[45%] h-64 lg:h-96 bg-surface-dark relative border border-white/5 overflow-hidden group flex-shrink-0">
                        <img src="https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_3.png" alt="Quietly Premium" class="absolute inset-0 w-full h-full object-cover transition-transform duration-1000 group-hover:scale-105" data-cms="specimens/block3/image" />
                    </div>
                    <div class="w-full lg:w-[55%] flex flex-col justify-center">
                        <div class="w-12 h-px bg-accent-bronze mb-6"></div>
                        <h3 class="font-serif text-2xl text-ivory mb-6 font-medium" data-cms="specimens/block3/title">Quietly Premium</h3>
                        <p class="text-ivory-dim font-light leading-relaxed text-sm md:text-base" data-cms="specimens/block3/body">
                            A refined interior anchored by a living specimen — naturally filtering air, softening acoustics, and enhancing well-being through biophilic design, creating a welcoming space that feels calm, intentional, and quietly premium.
                        </p>
                    </div>
                </div>

                <!-- Block 4: Text Left, Image Right -->
                <div class="flex flex-col lg:flex-row-reverse items-center gap-12 lg:gap-20">
                    <div class="w-full lg:w-[45%] h-64 lg:h-96 bg-surface-dark relative border border-white/5 overflow-hidden group flex-shrink-0">
                        <img src="https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_4.png" alt="Collector's Edition" class="absolute inset-0 w-full h-full object-cover transition-transform duration-1000 group-hover:scale-105" data-cms="specimens/block4/image" />
                    </div>
                    <div class="w-full lg:w-[55%] flex flex-col justify-center lg:items-start lg:text-left">
                        <div class="w-12 h-px bg-accent-bronze mb-6"></div>
                        <h3 class="font-serif text-2xl text-ivory mb-6 font-medium" data-cms="specimens/block4/title">Collector's Edition</h3>
                        <p class="text-ivory-dim font-light leading-relaxed text-sm md:text-base" data-cms="specimens/block4/body">
                            Singular botanical expressions reserved for spaces that demand rarity, permanence, and cultivated visual restraint.
                        </p>
                    </div>
                </div>
            </section>

            <!-- Concluding Section -->
            <section class="py-24 bg-[#0a0a0a] border-t border-white/5 text-center mt-8">
                <p class="font-serif text-2xl md:text-4xl lg:text-5xl text-ivory leading-tight" data-cms="specimens/closing/title">
                    Not just added.<br>
                    <span class="text-accent-bronze italic font-light">Introduced.</span>
                </p>
            </section>
        </main>"""

with open('curated-specimens.html', 'r') as f:
    html = f.read()

# Replace everything from <main to </main>
import re
new_full_html = re.sub(r'<main class="flex-grow pt-32 lg:pt-48">.*?</main>', new_html_content, html, flags=re.DOTALL)
with open('curated-specimens.html', 'w') as f:
    f.write(new_full_html)
print("Updated curated-specimens.html")
