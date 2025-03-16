import os
import json
import anthropic
from typing import List, Dict, Any

# Initialize the Anthropic client
# ANTHROPIC_API_KEY = "" 
client = anthropic.Anthropic(api_key = ANTHROPIC_API_KEY)

# Load seed data from JSON file
def load_seed_data(file_path: str) -> List[Dict[str, str]]:
    """
    Load seed examples from a JSON file.
    
    Args:
        file_path (str): Path to the seed data JSON file.
    
    Returns:
        List[Dict[str, str]]: List of seed examples (instruction, input, output).
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            seed_data = json.load(f)
        return seed_data
    except Exception as e:
        raise ValueError(f"Failed to load seed data from {file_path}: {str(e)}")

# Generate new instructions using Anthropic API (messages.create)
def generate_new_instructions(
    seed_examples: List[Dict[str, str]], 
    num_instructions: int = 10,
    temperature: float = 0.7
) -> List[str]:
    """
    Generate new fortune-telling instructions using Anthropic API.
    
    Args:
        seed_examples (List[Dict[str, str]]): List of seed examples for in-context learning.
        num_instructions (int): Number of new instructions to generate.
        temperature (float): Temperature for controlling creativity (0.0 to 1.0).
    
    Returns:
        List[str]: List of new instructions.
    """
    # Select 2-5 seed examples for in-context learning
    seed_subset = seed_examples[:min(5, len(seed_examples))]

    # Format seed examples for the prompt
    seed_prompt = "以下是命理相關的指令範例，請參考這些範例生成新的命理指令。\n\n"
    for i, example in enumerate(seed_subset, 1):
        seed_prompt += f"### 範例 {i}\n"
        seed_prompt += f"指令: {example['instruction']}\n"
        seed_prompt += f"輸入: {example['input']}\n"
        seed_prompt += f"輸出: {example['output']}\n\n"
    
    # Add instruction for generating new instructions
    seed_prompt += f"現在，請生成{num_instructions}個新的命理指令。"

    try:
        # Call Anthropic API for message completion
        message = client.messages.create(
            model="claude-3-7-sonnet-20250219",  # Replace with appropriate model
            max_tokens=500,
            temperature=temperature,
            messages=[
                {"role": "user", "content": seed_prompt}
            ]
        )
        
        # Extract and clean generated instructions
        generated_text = message.content[0].text.strip()  # Access text from content
        new_instructions = [line.strip() for line in generated_text.split("\n") if line.strip()]
        return new_instructions[:num_instructions]  # Limit to requested number
    except Exception as e:
        print(f"Error generating instructions: {str(e)}")
        return []

# Generate outputs for new instructions using Anthropic API (messages.create)
def generate_outputs(
    seed_examples: List[Dict[str, str]], 
    new_instructions: List[str],
    batch_size: int = 5,
    temperature: float = 0.7
) -> List[Dict[str, str]]:
    """
    Generate outputs for new fortune-telling instructions using Anthropic API.
    
    Args:
        seed_examples (List[Dict[str, str]]): List of seed examples for in-context learning.
        new_instructions (List[str]): List of new instructions to generate outputs for.
        batch_size (int): Number of instructions to process in each batch.
        temperature (float): Temperature for controlling creativity (0.0 to 1.0).
    
    Returns:
        List[Dict[str, str]]: List of new examples (instruction, input, output).
    """
    # Select 2-5 seed examples for in-context learning
    seed_subset = seed_examples[:min(5, len(seed_examples))]

    # Format seed examples for the prompt
    seed_prompt_base = "以下是命理相關的指令範例，請參考這些範例為新的指令生成輸出。\n\n"
    for i, example in enumerate(seed_subset, 1):
        seed_prompt_base += f"### 範例 {i}\n"
        seed_prompt_base += f"指令: {example['instruction']}\n"
        seed_prompt_base += f"輸入: {example['input']}\n"
        seed_prompt_base += f"輸出: {example['output']}\n\n"

    new_examples = []

    # Process instructions in batches
    for batch_start in range(0, len(new_instructions), batch_size):
        batch_instructions = new_instructions[batch_start:batch_start + batch_size]
        
        # Format prompt for the batch
        batch_prompt = seed_prompt_base + "以下是新指令，請為每個指令生成輸出。\n\n"
        for i, instruction in enumerate(batch_instructions, 1):
            batch_prompt += f"### 新指令 {i}\n"
            batch_prompt += f"指令: {instruction}\n"
            batch_prompt += "輸入: \n"  # Leave input empty for simplicity; modify if needed
            batch_prompt += "輸出: \n"

        try:
            # Call Anthropic API for message completion
            message = client.messages.create(
                model="claude-3-7-sonnet-20250219",  # Replace with appropriate model
                max_tokens=1000,  # Adjust based on output length
                temperature=temperature,
                messages=[
                    {"role": "user", "content": batch_prompt}
                ]
            )

            # Parse generated outputs
            generated_text = message.content[0].text.strip()  # Access text from content
            outputs = []
            current_output = ""
            current_instruction = ""
            parsing_output = False

            for line in generated_text.split("\n"):
                line = line.strip()
                if line.startswith("指令:"):
                    if current_output and current_instruction:
                        outputs.append((current_instruction, current_output))
                    current_instruction = line.replace("指令:", "").strip()
                    parsing_output = False
                elif line.startswith("輸出:"):
                    parsing_output = True
                    current_output = line.replace("輸出:", "").strip()
                elif parsing_output and line:
                    current_output += " " + line

            # Add the last output
            if current_output and current_instruction:
                outputs.append((current_instruction, current_output))

            # Create new examples
            for instruction, output in outputs:
                new_examples.append({
                    "instruction": instruction,
                    "input": "",  # Leave empty for now; modify if needed
                    "output": output
                })

        except Exception as e:
            print(f"Error generating outputs for batch {batch_start // batch_size + 1}: {str(e)}")

    return new_examples

# Save generated data to JSON file
def save_generated_data(data: List[Dict[str, str]], output_file: str):
    """
    Save generated examples to a JSON file.
    
    Args:
        data (List[Dict[str, str]]): List of generated examples (instruction, input, output).
        output_file (str): Path to save the generated data.
    """
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Generated data saved to {output_file}")
    except Exception as e:
        print(f"Error saving data to {output_file}: {str(e)}")

# Main function to generate fortune-telling data
def main():
    # Load seed data
    seed_data = load_seed_data("./seed_data.json")
    print(f"Loaded {len(seed_data)} seed examples.")

    # Generate new instructions
    new_instructions = generate_new_instructions(seed_data, num_instructions=10)
    print("\nGenerated new instructions:")
    for i, instruction in enumerate(new_instructions, 1):
        print(f"{i}. {instruction}")

    # Generate outputs for new instructions
    new_examples = generate_outputs(seed_data, new_instructions, batch_size=5)
    print("\nGenerated new examples:")
    for i, example in enumerate(new_examples, 1):
        print(f"{i}. Instruction: {example['instruction']}")
        print(f"   Input: {example['input']}")
        print(f"   Output: {example['output']}\n")

    # Save generated data
    save_generated_data(new_examples, "generated_data.json")

if __name__ == "__main__":
    main()